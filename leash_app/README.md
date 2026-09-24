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
| `wallet/rule_writer.py` | One Claude call that turns plain-text rules, and an optional product photo, into Q/A policies (on `/rules/`, reviewed before saving; not in the decision path) |
| `wallet/captions.py` | Captions for product images (`image_url` on a cart line) so Jev knows what a photo shows; Claude Haiku 4.5 (`CAPTION_MODEL`), untrusted, time-boxed to 3 s, cached |
| `wallet/handler.py` | Builds the Jev state, runs both Jev calls at once, stores the result |
| `wallet/offline.py` | Turns the challenge CSVs into live-shaped events |
| `wallet/leash_api.py` | Viseca Leash API client, decision delivery, customer answers (`/resolve`) |
| `wallet/templates/queue.html` | Mobile step-up queue: one card per purchase waiting for the customer; swipe right approves, left declines (answers go to `/resolve` for live runs) |
| `wallet/views.py` · `urls.py` | Dashboard, step-up queue, policy panel, history viewer, try page, live-API panel, `/api/evaluate` |
| `wallet/management/commands/` | `replay_offline`, `evaluate_accuracy`, `evaluate_injection`, `leash_worker` |

The Handler adds **pre-computed facts** to the state: rolling 7-day spend, earlier purchases at the merchant, device and country familiarity, and identical recent orders. It does this because Jev is documented as weak at arithmetic and date windows. Everything the shop wrote (product names, categories, details, description, image captions) sits under `merchant_text_untrusted`; the cart itself keeps only quantities and prices.

**Prompt-injection defence, three layers:** the fence above; a third Jev call that sees *only* the shop's text and answers one yes/no question (does it try to steer the payment decision?), plus a keyword check; and a plain-code guard: when either fires, the wallet never approves on its own (an approval becomes `step_up`, a decline stays a decline). `python manage.py evaluate_injection` attacks 16 purchases with 6 payloads in 3 text locations.

## Run

```bash
cd leash_app
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver          # http://127.0.0.1:8000
```

Keys live in `.env` (`TYPESAFE_API_KEY`, `TEAM_API_KEY`, and `ANTHROPIC_API_KEY` for the rule writer); it is git-ignored.
Dependencies: `django python-dotenv httpx anthropic`.

```bash
# Offline: replay a scenario from viseca-2026/data (read-only) through the Handler
.venv/bin/python manage.py replay_offline SCEN0001 --customer-answer decline

# Live: after creating + confirming a mandate and starting a run on /connector/
.venv/bin/python manage.py leash_worker
```

`POST /api/evaluate` accepts an `authorization.request` event, a poll envelope (`{"data": event}`),
or `{"query": event, "run_id": "..."}` and returns the decision, probabilities and policy scores.
