"""Replay a scenario from the CSVs through the Handler, in replay_order, as one run.

    python manage.py replay_offline SCEN0001
    python manage.py replay_offline SCEN0001 --customer-answer decline
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from wallet import offline
from wallet.handler import evaluate


class Command(BaseCommand):
    help = "Run one scenario's purchase attempts through the Handler (offline, no Leash API)."

    def add_arguments(self, parser):
        parser.add_argument("scenario", help="e.g. SCEN0001")
        parser.add_argument(
            "--customer-answer",
            choices=["approve", "decline"],
            help="Simulate the customer's answer to every step_up (default: leave them pending).",
        )

    def handle(self, scenario, customer_answer=None, **_):
        run_id = f"offline-{scenario}-{datetime.now():%Y%m%d-%H%M%S}"
        events = offline.events_for(scenario, live_prefix=f"{run_id}-")
        self.stdout.write(f"{run_id}: {len(events)} attempts\n")
        for event in events:
            ev = evaluate(event, source="offline", run_id=run_id)
            if ev.decision == "step_up" and customer_answer:
                ev.resolution, ev.resolved_at = customer_answer, timezone.now()
                ev.save(update_fields=["resolution", "resolved_at"])
            probs = "  ".join(
                f"{k[:3]} {v:.2f}" for k, v in (("approved", ev.p_approved), ("rejected", ev.p_rejected), ("review", ev.p_review)) if v is not None
            )
            weakest = min((s for s in ev.policy_scores if s["score"] is not None), key=lambda s: s["score"], default=None)
            self.stdout.write(
                f"#{event['authorization']['replay_order']:>2} {ev.source_authorization_id} "
                f"CHF {ev.amount_chf:>8} {ev.merchant_name[:18]:<18} -> {ev.decision:<8} [{probs}] "
                f"{ev.latency_ms:>4} ms"
                + (f"  weakest: {weakest['Q'][:40]} ({weakest['score']:.2f})" if weakest else "")
                + (f"  ERROR {ev.error}" if ev.error else "")
            )
        self.stdout.write(self.style.SUCCESS(f"Done. View it at /history/?run={run_id}"))
