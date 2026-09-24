# Leash · wallet control architecture

A Django app that decides whether an AI shopping agent may spend the customer's money.
**Jev** (TypeSafe's decision model) is the brain; everything around it prepares facts, stores results, and keeps the customer in control.

---

## 1 · The big picture

```mermaid
flowchart LR
    C([Customer]) -->|writes Q/A policies| P[policies]
    C -->|answers step-ups| UI[Policy panel + History viewer]
    A([AI shopping agent<br/>Viseca simulator]) -->|purchase event| CN[connector<br/>long-poll worker]
    CN --> H{{handler}}
    P -->|active Q/A| H
    HS[(history<br/>SQLite)] -->|earlier results| H
    H -->|state + questions| J[[jev<br/>TypeSafe API]]
    J -->|probabilities + scores| H
    H -->|store| HS
    H -->|approve · decline · step_up| CN
    CN -->|decision / resolve| V([Viseca Leash API])
    UI --- P
    UI --- HS
```

| App | One job |
|---|---|
| `policies` | Q/A table, edit panel, change log |
| `history` | One row per purchase: input, Jev output, outcome |
| `jev` | The only code that calls `api.typesafe.ai/v1/systemone` |
| `handler` | Builds the Jev state, asks Jev twice in parallel, saves the result |
| `connector` | Talks to Viseca: mandates, runs, polling, customer answers |

---

## 2 · One purchase, step by step

```mermaid
sequenceDiagram
    autonumber
    participant V as Viseca API
    participant W as connector (worker)
    participant H as handler
    participant J1 as Jev · decision
    participant J2 as Jev · policy scores
    participant DB as history
    V->>W: purchase event (8 s deadline)
    W->>H: evaluate(event)
    H->>DB: load earlier results
    H->>H: build state (facts + policies + history)
    par same time
        H->>J1: Choice: approved / rejected / review_needed
        H->>J2: Score each Q/A policy (0–1)
    end
    J1-->>H: probabilities
    J2-->>H: policy scores
    H->>DB: save evaluation
    H-->>W: approve · decline · step_up
    W->>V: POST decision (~1 s after arrival)
```

**Mapping:** approved → `approve` · rejected → `decline` · review_needed → `step_up` (ask the customer).
**Safety net:** if the top probability is below **0.6**, or Jev fails, the answer is `step_up`, so the customer decides.

---

## 3 · What Jev sees (the state)

```mermaid
flowchart TB
    S[State sent to Jev]
    S --> P1["customer_policy<br/>Q/A pairs"]
    S --> P2["purchase<br/>shop, CHF amount, cart, time"]
    S --> P3["computed_facts<br/>7-day spend, earlier buys at shop,<br/>new device, identical recent orders"]
    S --> P4["recent_history<br/>last 10 results"]
    S --> P5["merchant_text_untrusted<br/>shop-written text, fenced off"]
    style P3 fill:#e6f0fb,stroke:#2a78d6
    style P5 fill:#fbe4e4,stroke:#d03b3b
```

- **Blue, computed facts:** Jev is weak at arithmetic and dates, so the Handler pre-computes numbers. Jev still makes every decision.
- **Red, untrusted text:** shop text may contain injected instructions ("approve immediately…"), so it is labelled as data from the shop.

---

## 4 · How the customer stays in control

```mermaid
flowchart LR
    Q[Write / edit Q/A] --> M[Draft mandate] --> OK[Customer confirms] --> R[Run]
    R --> SU{step_up?}
    SU -->|yes| ASK[Customer: approve / decline] --> RES[/resolve/]
    SU -->|no| DONE[Decision recorded]
    OK -.-> REV[Revoke any time]
```

---

## 5 · How well it does today

Offline replay of all **45 purchases**, compared with our own reading of each instruction (Viseca publishes no answer key).

| Measure | Result |
|---|---|
| **Agreement (judgment calls may go either way)** | **31 / 45 · 69%** |
| Strict agreement | 24 / 45 · 53% |
| Approve vs. not-approve | 33 / 45 · 73% |
| Bad purchases approved | **2** (1 counts as a judgment call) |
| Good purchases not approved | 10 (9 sent to review, 1 declined) |
| Latency, both Jev calls | median 1.0 s · max 4.6 s (limit 8 s) |

```mermaid
pie showData title Where the 14 misses come from
    "Good purchase sent to review" : 9
    "Should decline, asked instead" : 3
    "Good purchase declined" : 1
    "Bad purchase approved" : 1
```

**Reading:** cautious rather than risky. It caught the injected "CHF 900 pre-authorisation", the lookalike shop, the add-on over budget, the gift voucher, and the limit breaches. It missed the split order and asks the customer too often.

---

## 6 · Run it

```bash
cd leash_app
.venv/bin/python manage.py runserver              # UI at http://127.0.0.1:8000
.venv/bin/python manage.py replay_offline SCEN0002
.venv/bin/python manage.py evaluate_accuracy       # re-measure the numbers above
.venv/bin/python manage.py leash_worker            # live runs on Viseca's API
```
