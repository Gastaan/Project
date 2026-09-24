"""All tables: the customer's Q/A policy, evaluated purchases, and Leash mandates/runs."""
from django.db import models

LABELS = [("approved", "Approved"), ("rejected", "Rejected"), ("review_needed", "Review needed")]
DECISIONS = [("approve", "approve"), ("decline", "decline"), ("step_up", "step_up")]
LABEL_TO_DECISION = {"approved": "approve", "rejected": "decline", "review_needed": "step_up"}


# --- Policies ---------------------------------------------------------------

class Policy(models.Model):
    question = models.TextField()
    answer = models.TextField()
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"Q: {self.question} / A: {self.answer}"

    def as_pair(self):
        return {"id": self.id, "Q": self.question, "A": self.answer}


class PolicyEvent(models.Model):
    """Every create / edit / toggle / delete, so the customer can see what changed and when."""

    ACTIONS = [(a, a) for a in ("created", "edited", "activated", "deactivated", "deleted")]
    policy_id = models.BigIntegerField()
    action = models.CharField(max_length=16, choices=ACTIONS)
    question = models.TextField()
    answer = models.TextField()
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at", "-id"]

    @classmethod
    def record(cls, policy, action):
        return cls.objects.create(policy_id=policy.id, action=action, question=policy.question, answer=policy.answer)


def active_policies():
    return list(Policy.objects.filter(is_active=True))


# --- History ----------------------------------------------------------------

class Evaluation(models.Model):
    """One evaluated purchase: what came in, what Jev said, what was decided, what the customer answered."""

    SOURCES = [("api", "API / try page"), ("offline", "Offline replay"), ("live", "Live Leash run")]

    created_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=8, choices=SOURCES, default="api")

    run_id = models.CharField(max_length=64, blank=True, db_index=True)
    authorization_id = models.CharField(max_length=64, db_index=True)
    source_authorization_id = models.CharField(max_length=64, blank=True)
    scenario_id = models.CharField(max_length=16, blank=True)
    card_id = models.CharField(max_length=32, blank=True, db_index=True)
    merchant_id = models.CharField(max_length=32, blank=True)
    merchant_name = models.CharField(max_length=128, blank=True)
    amount_chf = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    sim_timestamp = models.DateTimeField(null=True, db_index=True)

    query = models.JSONField()
    state = models.JSONField(default=dict)
    policies_snapshot = models.JSONField(default=list)

    p_approved = models.FloatField(null=True)
    p_rejected = models.FloatField(null=True)
    p_review = models.FloatField(null=True)
    confidence = models.FloatField(null=True)
    label = models.CharField(max_length=16, choices=LABELS)
    decision = models.CharField(max_length=8, choices=DECISIONS)
    policy_scores = models.JSONField(default=list)
    injection_score = models.FloatField(null=True)  # Jev: probability the shop's text tries to steer the decision
    reason = models.TextField(blank=True)
    jev_model = models.CharField(max_length=32, blank=True)
    jev_usage = models.JSONField(default=dict)
    latency_ms = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    posted = models.BooleanField(default=False)
    post_status = models.CharField(max_length=255, blank=True)
    resolution = models.CharField(max_length=8, blank=True, choices=[("approve", "approve"), ("decline", "decline")])
    resolved_at = models.DateTimeField(null=True)
    resolve_status = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["run_id", "authorization_id"], name="one_evaluation_per_run_authorization")
        ]

    @property
    def outcome(self):
        """Final effect on the customer's money: approved, declined, or still waiting on the customer."""
        if self.decision == "step_up":
            return {"approve": "approved", "decline": "declined"}.get(self.resolution, "pending")
        return "approved" if self.decision == "approve" else "declined"

    def summary(self):
        """Compact row fed back to Jev as history for later queries."""
        return {
            "when": self.sim_timestamp.isoformat() if self.sim_timestamp else None,
            "merchant": self.merchant_name,
            "amount_chf": float(self.amount_chf) if self.amount_chf is not None else None,
            "items": [line.get("item_name") for line in self.query.get("authorization", {}).get("items", [])],
            "result": self.outcome,
        }


# --- Leash API records (the API remains the source of truth) ---------------

class Mandate(models.Model):
    draft_id = models.CharField(max_length=64)
    mandate_id = models.CharField(max_length=64, blank=True)
    scenario_id = models.CharField(max_length=16)
    instruction = models.TextField()
    guidance = models.JSONField(default=list)
    status = models.CharField(max_length=16, default="draft")  # draft / active / revoked
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Run(models.Model):
    run_id = models.CharField(max_length=64, unique=True)
    scenario_id = models.CharField(max_length=16)
    mandate_id = models.CharField(max_length=64)
    started_at = models.DateTimeField(auto_now_add=True)
    last_status = models.JSONField(default=dict)

    class Meta:
        ordering = ["-started_at"]
