"""Viseca's Leash sandbox API: the HTTP client plus delivery of decisions and customer answers."""
import httpx
from django.conf import settings
from django.utils import timezone

from .models import Evaluation

ENGINE_VERSION = "leash-app-jev-0.1"


class LeashError(Exception):
    def __init__(self, status, body):
        super().__init__(f"Leash API {status}: {body}")
        self.status, self.body = status, body


class LeashClient:
    """Endpoints from technical_details.md, 'All API calls in one place'."""

    def __init__(self, base_url=None, key=None, timeout=30.0):
        key = key or settings.TEAM_API_KEY
        if not key:
            raise LeashError(0, "TEAM_API_KEY is not set")
        self.http = httpx.Client(
            base_url=(base_url or settings.LEASH_BASE_URL).rstrip("/"),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=timeout,
        )

    def _call(self, method, path, **kw):
        resp = self.http.request(method, path, **kw)
        if resp.status_code == 204:
            return None
        body = resp.json() if resp.content else None
        if resp.status_code >= 400:
            raise LeashError(resp.status_code, body)
        return body

    def bootstrap(self):
        return self._call("GET", "/v1/bootstrap")

    def get_run(self, run_id):
        return self._call("GET", f"/v1/scenario-runs/{run_id}")

    def create_mandate(self, instruction, guidance, hard_rules=None, uncertainty_policy="ask", open_questions=None):
        return self._call("POST", "/v1/mandates", json={
            "instruction": instruction,
            "hard_rules": hard_rules or [],
            "uncertainty_policy": uncertainty_policy,
            "guidance": guidance,
            "open_questions": open_questions or [],
        })

    def confirm_mandate(self, draft_id):
        return self._call("POST", f"/v1/mandates/{draft_id}/confirm", json={"confirmed": True})

    def revoke_mandate(self, mandate_id):
        return self._call("DELETE", f"/v1/mandates/{mandate_id}")

    def start_run(self, scenario_id, mandate_id):
        return self._call("POST", "/v1/scenario-runs", json={"scenario_id": scenario_id, "mandate_id": mandate_id})

    def next_request(self, wait=25):
        resp = self.http.get("/v1/decision-requests/next", params={"wait": wait}, timeout=wait + 10)
        if resp.status_code == 204:
            return None
        if resp.status_code >= 400:
            raise LeashError(resp.status_code, resp.text[:500])
        return resp.json()

    def post_decision(self, payload):
        return self._call("POST", f"/v1/authorizations/{payload['authorization_id']}/decision", json=payload)

    def resolve(self, authorization_id, decision, customer_message, evidence=None):
        return self._call("POST", f"/v1/authorizations/{authorization_id}/resolve", json={
            "decision": decision, "customer_message": customer_message, "evidence": evidence or [],
        })


def decision_payload(ev: Evaluation) -> dict:
    codes = [f"jev_{ev.label}"]
    codes += [f"policy_{s['policy_id']}_low" for s in ev.policy_scores if s.get("score") is not None and s["score"] < 0.5]
    if ev.error:
        codes.append("jev_unavailable_fallback")
    evidence = [
        f"P(approved)={ev.p_approved:.2f}, P(rejected)={ev.p_rejected:.2f}, P(review_needed)={ev.p_review:.2f}"
        if ev.p_approved is not None else "Jev probabilities unavailable",
    ]
    evidence += [f"Q: {s['Q']} | A: {s['A']} | score {s['score']:.2f}" for s in ev.policy_scores if s.get("score") is not None]
    return {
        "authorization_id": ev.authorization_id,
        "decision": ev.decision,
        "reason_codes": codes,
        "customer_message": ev.reason[:1000],
        "evidence": evidence,
        "engine_version": ENGINE_VERSION,
    }


def post_decision(ev: Evaluation, client: LeashClient) -> None:
    try:
        client.post_decision(decision_payload(ev))
        ev.posted, ev.post_status = True, "accepted"
    except LeashError as exc:
        ev.post_status = str(exc)[:255]
        ev.posted = exc.status == 409  # a conflict usually means this decision was already recorded (a retry)
    ev.save(update_fields=["posted", "post_status"])


def resolve(ev: Evaluation, answer: str, client: LeashClient | None = None) -> None:
    """Record the customer's answer to a step_up. Live evaluations are also sent to /resolve."""
    ev.resolution, ev.resolved_at = answer, timezone.now()
    if ev.source == "live":
        message = "The customer approved this purchase." if answer == "approve" else "The customer declined this purchase."
        try:
            (client or LeashClient()).resolve(ev.authorization_id, answer, message)
            ev.resolve_status = "accepted"
        except LeashError as exc:
            ev.resolve_status = str(exc)[:255]
    else:
        ev.resolve_status = "recorded locally"
    ev.save(update_fields=["resolution", "resolved_at", "resolve_status"])
