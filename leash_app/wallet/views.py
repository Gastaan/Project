"""All pages: dashboard, policy panel, history viewer, try page, live-API panel, and POST /api/evaluate."""
import json
from datetime import datetime
from urllib.parse import urlencode

from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import leash_api, offline
from .handler import evaluate
from .leash_api import LeashClient, LeashError
from .models import Evaluation, Mandate, Policy, PolicyEvent, Run, active_policies

# Example Q/A sets written from each scenario's cardholder instruction. The customer edits them freely.
PRESETS = {
    "SCEN0000 · Connection check": [
        ("How much may one purchase cost?", "CHF 20 or less, delivery included."),
        ("What may the agent buy?", "One ordinary grocery item."),
        ("Which shops may the agent use?", "Only shops I use regularly."),
        ("What if something is unclear?", "Ask me."),
    ],
    "SCEN0001 · Household budget": [
        ("What may the agent buy?", "Our household groceries, delivered."),
        ("How much may one order cost?", "CHF 120 or less, including delivery."),
        ("How much may be spent across any seven days?", "CHF 300 or less in total."),
        ("What if something is unclear?", "Ask me."),
    ],
    "SCEN0002 · Requested item and order terms": [
        ("What may the agent buy?", "One pair of road-running shoes in size 43, to replace my worn pair."),
        ("Which shops may the agent use?", "Only specialist sports retailers."),
        ("Which return terms are required?", "The order must be returnable within 14 days or more."),
        ("How much may be spent?", "No more than CHF 200."),
        ("What if something is unclear?", "Ask me."),
    ],
    "SCEN0003 · Session integrity": [
        ("What may the agent buy?", "Clothing for me."),
        ("How much may one order cost?", "Up to CHF 250 per order."),
        ("Which shops may the agent use?", "Only shops I have used before."),
        ("What if it looks like someone else is driving the session?", "Pause it and ask me."),
        ("What if something is unclear?", "Ask me."),
    ],
    "SCEN0004 · Manipulated agent": [
        ("What may the agent buy?", "The 27-inch monitor I chose, and nothing else."),
        ("Which sellers may the agent use?", "Only sellers I have bought from before."),
        ("How much may be spent?", "CHF 400 or less."),
        ("May the agent add extras to the cart?", "No. Do not add anything I did not ask for."),
        ("What if something is unclear?", "Ask me."),
    ],
}


# --- Dashboard ---------------------------------------------------------------

def dashboard(request):
    counts = dict(Evaluation.objects.values_list("label").annotate(n=Count("id")))
    return render(request, "dashboard.html", {
        "counts": counts,
        "total": sum(counts.values()),
        "recent": Evaluation.objects.all()[:8],
        "policies": Policy.objects.filter(is_active=True),
        "jev_ready": bool(settings.TYPESAFE_API_KEY),
        "leash_ready": bool(settings.TEAM_API_KEY),
        "review_floor": settings.REVIEW_FLOOR,
    })


# --- Policies ----------------------------------------------------------------

def policy_list(request):
    return render(request, "policies.html", {
        "policies": Policy.objects.all(),
        "events": PolicyEvent.objects.all()[:30],
        "presets": list(PRESETS),
    })


@require_POST
def policy_add(request):
    q, a = request.POST.get("question", "").strip(), request.POST.get("answer", "").strip()
    if q and a:
        last = Policy.objects.order_by("-position").first()
        p = Policy.objects.create(question=q, answer=a, position=(last.position + 1) if last else 1)
        PolicyEvent.record(p, "created")
    return redirect("policy_list")


@require_POST
def policy_edit(request, pk):
    p = get_object_or_404(Policy, pk=pk)
    q, a = request.POST.get("question", "").strip(), request.POST.get("answer", "").strip()
    position = request.POST.get("position", "").strip()
    if q and a and (q, a) != (p.question, p.answer):
        p.question, p.answer = q, a
        PolicyEvent.record(p, "edited")
    if position.isdigit():
        p.position = int(position)
    p.save()
    return redirect("policy_list")


@require_POST
def policy_toggle(request, pk):
    p = get_object_or_404(Policy, pk=pk)
    p.is_active = not p.is_active
    p.save()
    PolicyEvent.record(p, "activated" if p.is_active else "deactivated")
    return redirect("policy_list")


@require_POST
def policy_delete(request, pk):
    p = get_object_or_404(Policy, pk=pk)
    PolicyEvent.record(p, "deleted")
    p.delete()
    return redirect("policy_list")


@transaction.atomic
def activate_preset(name):
    """Switch the current active rows off and add the named example set as the active policy."""
    for p in Policy.objects.filter(is_active=True):
        p.is_active = False
        p.save()
        PolicyEvent.record(p, "deactivated")
    start = (Policy.objects.order_by("-position").values_list("position", flat=True).first() or 0) + 1
    for i, (q, a) in enumerate(PRESETS[name]):
        PolicyEvent.record(Policy.objects.create(question=q, answer=a, position=start + i), "created")


@require_POST
def policy_load_preset(request):
    if request.POST.get("preset") in PRESETS:
        activate_preset(request.POST["preset"])
    return redirect("policy_list")


# --- History -------------------------------------------------------------------

def history_list(request):
    qs = Evaluation.objects.all()
    filters = {k: request.GET.get(k, "") for k in ("label", "decision", "source", "run", "q")}
    for field, key in (("label", "label"), ("decision", "decision"), ("source", "source"), ("run_id", "run")):
        if filters[key]:
            qs = qs.filter(**{field: filters[key]})
    if filters["q"]:
        qs = qs.filter(merchant_name__icontains=filters["q"]) | qs.filter(authorization_id__icontains=filters["q"])
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    runs = sorted(set(Evaluation.objects.exclude(run_id="").values_list("run_id", flat=True)))
    return render(request, "history_list.html", {"page": page, "filters": filters, "runs": runs})


def history_detail(request, pk):
    ev = get_object_or_404(Evaluation, pk=pk)
    earlier = (
        Evaluation.objects.filter(run_id=ev.run_id, sim_timestamp__lt=ev.sim_timestamp).order_by("sim_timestamp")
        if ev.run_id and ev.sim_timestamp else []
    )
    return render(request, "history_detail.html", {
        "ev": ev,
        "earlier": earlier,
        "state_json": json.dumps(ev.state, indent=2, ensure_ascii=False),
        "query_json": json.dumps(ev.query, indent=2, ensure_ascii=False),
    })


# --- Try a purchase + JSON API ---------------------------------------------------

def serialize(ev):
    return {
        "id": ev.id,
        "authorization_id": ev.authorization_id,
        "label": ev.label,
        "decision": ev.decision,
        "probabilities": {"approved": ev.p_approved, "rejected": ev.p_rejected, "review_needed": ev.p_review},
        "confidence": ev.confidence,
        "policy_scores": ev.policy_scores,
        "reason": ev.reason,
        "latency_ms": ev.latency_ms,
        "error": ev.error or None,
    }


def try_page(request):
    error = ""
    if request.method == "POST":
        try:
            if request.POST.get("attempt"):
                event = offline.event_for_attempt(request.POST["attempt"], f"TRY{datetime.now():%H%M%S}-")
            else:
                event = json.loads(request.POST.get("event_json", ""))
                event = event.get("data", event)  # accept a whole poll envelope too
            return redirect("history_detail", pk=evaluate(event, source="api").id)
        except (ValueError, KeyError, StopIteration) as exc:
            error = f"Could not evaluate that input: {exc}"
    attempts = offline.attempt_ids() if settings.DATA_DIR.exists() else []
    return render(request, "try.html", {"attempts": attempts, "error": error})


@csrf_exempt
@require_POST
def api_evaluate(request):
    """Body: an authorization.request event, a poll envelope ({"data": event}), or {"query": event, "run_id": "..."}."""
    try:
        body = json.loads(request.body)
        event = body.get("query") or body.get("data") or body
        ev = evaluate(event, source="api", run_id=body.get("run_id", ""))
    except (ValueError, KeyError, TypeError) as exc:
        return JsonResponse({"error": {"code": "bad_request", "message": str(exc)}}, status=400)
    return JsonResponse(serialize(ev))


# --- Live Leash API panel ---------------------------------------------------------

def _back(msg):
    return redirect(reverse("connector_panel") + "?" + urlencode({"msg": msg}))


def _client_or_none():
    try:
        return LeashClient(timeout=15)
    except LeashError:
        return None


def connector_panel(request):
    client, boot, error = _client_or_none(), None, ""
    if client:
        try:
            boot = client.bootstrap()
        except Exception as exc:  # network problems should not break the page
            error = str(exc)
    else:
        error = "TEAM_API_KEY is not set in leash_app/.env"
    return render(request, "connector.html", {
        "boot": boot, "error": error, "msg": request.GET.get("msg", ""),
        "mandates": Mandate.objects.all()[:20], "runs": Run.objects.all()[:20],
        "pending": Evaluation.objects.filter(decision="step_up", resolution="").order_by("-created_at"),
        "policies": active_policies(),
    })


@require_POST
def mandate_draft(request):
    """Create a draft mandate: the scenario's exact instruction + the active Q/A policies as guidance."""
    scenario_id = request.POST.get("scenario_id", "")
    try:
        client = LeashClient()
        boot = client.bootstrap()
        instruction = next(s["cardholder_instruction"] for s in boot["scenarios"] if s["scenario_id"] == scenario_id)
        guidance = [f"Q: {p.question} A: {p.answer}" for p in active_policies()]
        resp = client.create_mandate(instruction, guidance)
        Mandate.objects.create(draft_id=resp["draft_id"], scenario_id=scenario_id, instruction=instruction, guidance=guidance)
        return _back(f"Draft {resp['draft_id']} created. Review it, then confirm.")
    except (LeashError, StopIteration, KeyError) as exc:
        return _back(f"Could not create the draft: {exc}")


@require_POST
def mandate_confirm(request, pk):
    m = get_object_or_404(Mandate, pk=pk)
    try:
        m.mandate_id, m.status = LeashClient().confirm_mandate(m.draft_id)["mandate_id"], "active"
        m.save()
        return _back(f"Mandate {m.mandate_id} is active.")
    except (LeashError, KeyError) as exc:
        return _back(f"Confirm failed: {exc}")


@require_POST
def mandate_revoke(request, pk):
    m = get_object_or_404(Mandate, pk=pk)
    try:
        LeashClient().revoke_mandate(m.mandate_id)
        m.status = "revoked"
        m.save()
        return _back(f"Mandate {m.mandate_id} revoked.")
    except LeashError as exc:
        return _back(f"Revoke failed: {exc}")


@require_POST
def run_start(request, pk):
    m = get_object_or_404(Mandate, pk=pk)
    if request.POST.get("sure") != "yes":
        return _back("Tick the box to confirm you want to start a live run.")
    try:
        resp = LeashClient().start_run(m.scenario_id, m.mandate_id)
        Run.objects.create(run_id=resp["run_id"], scenario_id=m.scenario_id, mandate_id=m.mandate_id, last_status=resp)
        return _back(f"Run {resp['run_id']} started. Keep `python manage.py leash_worker` running.")
    except (LeashError, KeyError) as exc:
        return _back(f"Could not start the run: {exc}")


@require_POST
def run_refresh(request, pk):
    r = get_object_or_404(Run, pk=pk)
    try:
        r.last_status = LeashClient().get_run(r.run_id)
        r.save()
        return _back("Run status refreshed.")
    except LeashError as exc:
        return _back(f"Refresh failed: {exc}")


@require_POST
def resolve(request, pk):
    ev = get_object_or_404(Evaluation, pk=pk, decision="step_up")
    answer = request.POST.get("answer")
    if answer in ("approve", "decline") and not ev.resolution:
        leash_api.resolve(ev, answer, _client_or_none() if ev.source == "live" else None)
    return redirect(request.POST.get("next") or reverse("history_detail", kwargs={"pk": pk}))
