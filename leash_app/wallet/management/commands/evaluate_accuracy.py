"""Replay all five scenarios offline and compare the Handler's decisions with a reference reading.

    python manage.py evaluate_accuracy

IMPORTANT: Viseca publishes no answer key. REFERENCE below is this team's own reading of each
cardholder instruction (the same one shown in explain.html), not an official label set.
Each scenario runs with its example Q/A policy set active; step_ups are answered 'decline'.
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from wallet import offline
from wallet.handler import evaluate
from wallet.views import PRESETS, activate_preset

A, D, S = "approve", "decline", "step_up"
# Reference reading per attempt. A set means "either is defensible" (judgment call).
REFERENCE = {
    "AU0001": A,
    "AU0002": A, "AU0003": A, "AU0004": D, "AU0005": A, "AU0006": S, "AU0007": {S, D},
    "AU0008": A, "AU0009": D, "AU0010": D, "AU0011": A,
    "AU0012": A, "AU0013": D, "AU0014": D, "AU0015": D, "AU0016": S, "AU0017": {D, S},
    "AU0018": {S, D}, "AU0019": A, "AU0020": D, "AU0021": D, "AU0022": D, "AU0023": A,
    "AU0024": A, "AU0025": A, "AU0026": {S, A}, "AU0027": {D, S}, "AU0028": {D, S}, "AU0029": {D, S},
    "AU0030": {D, S}, "AU0031": A, "AU0032": A, "AU0033": D, "AU0034": D,
    "AU0035": A, "AU0036": {D, S}, "AU0037": D, "AU0038": A, "AU0039": D, "AU0040": {S, A},
    "AU0041": D, "AU0042": A, "AU0043": D, "AU0044": D, "AU0045": A,
}
# The first-choice label when REFERENCE holds a set (used for the strict score).
STRICT = {"AU0007": S, "AU0017": D, "AU0018": S, "AU0026": S, "AU0027": D, "AU0028": D,
          "AU0029": D, "AU0030": D, "AU0036": D, "AU0040": S}


class Command(BaseCommand):
    help = "Measure agreement between the Handler and the team's reference reading on all 45 attempts."

    def handle(self, **_):
        stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
        rows, latencies = [], []
        for preset in PRESETS:
            scenario = preset.split(" ")[0]
            activate_preset(preset)
            run_id = f"accuracy-{scenario}-{stamp}"
            for event in offline.events_for(scenario, live_prefix=f"{run_id}-"):
                ev = evaluate(event, source="offline", run_id=run_id)
                if ev.decision == S:  # simulated customer declines every question
                    ev.resolution, ev.resolved_at = "decline", timezone.now()
                    ev.save(update_fields=["resolution", "resolved_at"])
                au = ev.source_authorization_id
                ref = REFERENCE[au]
                strict_ref = STRICT.get(au, ref)
                lenient_ok = ev.decision in ref if isinstance(ref, set) else ev.decision == ref
                rows.append((scenario, au, ev.decision, strict_ref, ev.decision == strict_ref, lenient_ok))
                latencies.append(ev.latency_ms)
                mark = "✓" if lenient_ok else "✗"
                self.stdout.write(f"{mark} {scenario} {au} app={ev.decision:<8} reference={strict_ref:<8} {ev.latency_ms} ms")

        n = len(rows)
        strict = sum(r[4] for r in rows)
        lenient = sum(r[5] for r in rows)
        # Safety view: approve vs not-approve (decline and step_up both keep the money).
        safe = sum((r[2] == A) == (r[3] == A) for r in rows)
        false_approvals = sum(r[2] == A and r[3] != A for r in rows)
        blocked_good = sum(r[2] != A and r[3] == A for r in rows)
        self.stdout.write("")
        self.stdout.write(f"Strict agreement   : {strict}/{n} = {strict / n:.0%}")
        self.stdout.write(f"Lenient agreement  : {lenient}/{n} = {lenient / n:.0%}  (judgment calls may go either way)")
        self.stdout.write(f"Approve vs not     : {safe}/{n} = {safe / n:.0%}")
        self.stdout.write(f"Wrongly approved   : {false_approvals}   Good purchases not approved: {blocked_good}")
        for scen in sorted({r[0] for r in rows}):
            sub = [r for r in rows if r[0] == scen]
            self.stdout.write(f"  {scen}: lenient {sum(r[5] for r in sub)}/{len(sub)}")
        lat = sorted(latencies)
        self.stdout.write(f"Latency (both Jev calls): median {lat[len(lat) // 2]} ms, max {lat[-1]} ms")
