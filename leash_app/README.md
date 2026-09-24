# Leash · wallet control (Django + Jev)

Decides whether an AI shopping agent may spend the customer's money. Every purchase goes to the
**Handler** together with the customer's **Q/A policies** and the **history** of earlier results.
Jev (TypeSafe's System One model) answers twice, concurrently:

1. **Decision:** probabilities for `approved` / `rejected` / `review_needed` (one Choice question).
2. **Policy fit:** a 0–1 score for every active Q/A policy (one Score question each).

`approved → approve`, `rejected → decline`, `review_needed → step_up` (ask the customer).
If the top probability is below `REVIEW_FLOOR`, or Jev fails, the result is `review_needed`.

## Layout: one Django app (`wallet`), one file per module

| File | Role |
|---|---|
| `wallet/models.py` | Policy (Q/A) + change log, Evaluation (history), Mandate, Run |
| `wallet/jev.py` | The only code that calls `POST https://api.typesafe.ai/v1/systemone` |
| `wallet/handler.py` | Builds the Jev state, runs both Jev calls at once, stores the result |
| `wallet/offline.py` | Turns the challenge CSVs into live-shaped events |
| `wallet/leash_api.py` | Viseca Leash API client, decision delivery, customer answers (`/resolve`) |
| `wallet/views.py` · `urls.py` | Dashboard, policy panel, history viewer, try page, live-API panel, `/api/evaluate` |
| `wallet/management/commands/` | `replay_offline`, `evaluate_accuracy`, `leash_worker` |

The Handler adds **pre-computed facts** to the state: rolling 7-day spend, earlier purchases at the merchant, device and country familiarity, and identical recent orders. It does this because Jev is documented as weak at arithmetic and date windows. Merchant-written text sits under `merchant_text_untrusted`.

## Run

```bash
cd leash_app
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver          # http://127.0.0.1:8000
```

Keys live in `.env` (`TYPESAFE_API_KEY`, `TEAM_API_KEY`); it is git-ignored.

```bash
# Offline: replay a scenario from viseca-2026/data (read-only) through the Handler
.venv/bin/python manage.py replay_offline SCEN0001 --customer-answer decline

# Live: after creating + confirming a mandate and starting a run on /connector/
.venv/bin/python manage.py leash_worker
```

`POST /api/evaluate` accepts an `authorization.request` event, a poll envelope (`{"data": event}`),
or `{"query": event, "run_id": "..."}` and returns the decision, probabilities and policy scores.
