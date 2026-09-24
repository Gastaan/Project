"""Build live-shaped authorization.request events from the challenge CSVs (read-only).

Follows technical_details.md §3: numbers as numbers, nulls as null, nested merchant
and items, related_authorization_id mapped to this replay's live IDs.
"""
import csv
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from django.conf import settings


def _read(name):
    with open(settings.DATA_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _pack():
    merchants = {m["merchant_id"]: m for m in _read("merchants.csv")}
    lines = {}
    for r in _read("purchase_attempt_items.csv"):
        lines.setdefault(r["authorization_id"], []).append(r)
    attempts = _read("purchase_attempts.csv")
    catalogue = {s["scenario_id"]: s for s in _read("scenario_catalogue.csv")}
    authorities = {a["authority_id"]: a for a in _read("scenario_authorities.csv")}
    return merchants, lines, attempts, catalogue, authorities


def scenarios():
    return _pack()[3]


def attempt_ids():
    return [(a["authorization_id"], a["scenario_id"], int(a["replay_order"])) for a in _pack()[2]]


def _num(v):
    return None if v in ("", None) else float(v)


def build_event(row, live_prefix: str) -> dict:
    merchants, lines, _, catalogue, authorities = _pack()
    m = merchants[row["merchant_id"]]
    now = datetime.now(timezone.utc)
    live = lambda au: f"{live_prefix}{au}" if au else None  # noqa: E731
    authority = authorities[row["authority_id"]]
    return {
        "type": "authorization.request",
        "request_id": f"req_{live(row['authorization_id'])}",
        "deadline_at": (now + timedelta(seconds=8)).isoformat().replace("+00:00", "Z"),
        "authorization": {
            "authorization_id": live(row["authorization_id"]),
            "source_authorization_id": row["authorization_id"],
            "scenario_id": row["scenario_id"],
            "replay_order": int(row["replay_order"]),
            "mandate_id": "OFFLINE",
            "profile_id": f"PROFILE_{row['authority_id']}",
            "card_id": row["card_id"],
            "initiator_type": "agent",
            "merchant": {
                "merchant_id": m["merchant_id"],
                "merchant_name": m["merchant_name"],
                "merchant_category": m["merchant_category"],
                "merchant_mcc": m["merchant_mcc"],
                "merchant_country": m["merchant_country"],
                "merchant_city": m["merchant_city"],
                "availability": m["availability"],
                "recurring_capable": m["recurring_capable"],
            },
            "timestamp": row["timestamp"],
            "amount": float(row["amount"]),
            "currency": row["currency"],
            "billing_amount_chf": float(row["billing_amount_chf"]),
            "items_subtotal": float(row["items_subtotal"]),
            "delivery_fee": float(row["delivery_fee"]),
            "channel": row["channel"],
            "customer_device_id": row["customer_device_id"],
            "authority_status": row["authority_status"],
            "card_status_at_attempt": row["card_status_at_attempt"],
            "spend_in_period_before_chf": _num(row["spend_in_period_before_chf"]),
            "recent_attempt_count_10m": int(row["recent_attempt_count_10m"]),
            "fulfillment_method": row["fulfillment_method"],
            "delivery_by": row["delivery_by"] or None,
            "order_returnable": row["order_returnable"],
            "order_cancellable": row["order_cancellable"],
            "related_authorization_id": live(row["related_authorization_id"]),
            "related_authorization_status": row["related_authorization_status"] or None,
            "purchase_description": row["purchase_description"],
            "items": [
                {
                    "line_no": int(r["line_no"]),
                    "item_id": r["item_id"],
                    "item_name": r["item_name"],
                    "item_category": r["item_category"],
                    "quantity": int(r["quantity"]),
                    "unit_price": float(r["unit_price"]),
                    "currency": r["currency"],
                    "item_details": r["item_details"],
                }
                for r in sorted(lines.get(row["authorization_id"], []), key=lambda r: int(r["line_no"]))
            ],
        },
        "mandate": {
            "mandate_id": "OFFLINE",
            "status": "active",
            "customer_id": authority["customer_id"],
            "card_id": authority["card_id"],
            "instruction": catalogue[row["scenario_id"]]["cardholder_instruction"],
            "hard_rules": [],
            "uncertainty_policy": "ask",
            "profile_id": f"PROFILE_{row['authority_id']}",
        },
        "context": {"approved_spend_in_period_chf": None, "recent_authorizations": []},
        "runtime": {
            "received_at": now.isoformat().replace("+00:00", "Z"),
            "history_window_minutes": 10,
            "context_basis": "run_decisions_and_scenario_timestamps",
        },
    }


def events_for(scenario_id: str, live_prefix: str) -> list[dict]:
    rows = sorted((a for a in _pack()[2] if a["scenario_id"] == scenario_id), key=lambda a: int(a["replay_order"]))
    return [build_event(r, live_prefix) for r in rows]


def event_for_attempt(au_id: str, live_prefix: str = "TRY-") -> dict:
    row = next(a for a in _pack()[2] if a["authorization_id"] == au_id)
    return build_event(row, live_prefix)
