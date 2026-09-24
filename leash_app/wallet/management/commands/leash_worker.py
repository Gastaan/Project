"""Long-poll the Leash API and answer every purchase through the Handler.

    python manage.py leash_worker                 # run until Ctrl+C
    python manage.py leash_worker --idle-exit 3   # stop after 3 empty polls in a row

Outline follows technical_details.md §6: 204 = no work yet; the same live
authorization_id may arrive again (re-send the stored decision); decide before deadline_at.
"""
import time
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from wallet.handler import evaluate
from wallet.leash_api import LeashClient, post_decision


def _seconds_left(deadline_at):
    if not deadline_at:
        return None
    return (datetime.fromisoformat(deadline_at.replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds()


class Command(BaseCommand):
    help = "Poll /v1/decision-requests/next and post a decision for every purchase."

    def add_arguments(self, parser):
        parser.add_argument("--wait", type=int, default=25, help="Long-poll wait in seconds (max 25).")
        parser.add_argument("--idle-exit", type=int, default=0, help="Exit after this many empty polls in a row (0 = never).")

    def handle(self, wait, idle_exit, **_):
        client = LeashClient()
        self.stdout.write(self.style.SUCCESS(f"Worker started, polling every {wait}s. Ctrl+C to stop."))
        idle = 0
        while True:
            try:
                envelope = client.next_request(wait=wait)
            except Exception as exc:  # keep the worker alive through network blips
                self.stderr.write(f"poll failed: {exc}")
                time.sleep(2)
                continue
            if envelope is None:
                idle += 1
                if idle_exit and idle >= idle_exit:
                    self.stdout.write("No work left, exiting.")
                    return
                continue
            idle = 0
            event = envelope.get("data", {})
            run_id = envelope.get("run_id", "")
            auth = event.get("authorization", {})
            before = _seconds_left(event.get("deadline_at"))
            ev = evaluate(event, source="live", run_id=run_id)
            if not ev.posted:
                post_decision(ev, client)
            after = _seconds_left(event.get("deadline_at"))
            self.stdout.write(
                f"{run_id} #{auth.get('replay_order')} {auth.get('source_authorization_id')} "
                f"-> {ev.decision:<8} posted={ev.posted} ({ev.post_status}) "
                f"jev {ev.latency_ms} ms, {after if after is None else round(after, 1)}s left of {before if before is None else round(before, 1)}"
            )
