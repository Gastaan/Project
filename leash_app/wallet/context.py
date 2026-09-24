"""Template context shared by every page."""
from .models import Evaluation


def pending_count(request):
    """Number of purchases waiting for the customer, shown as a badge in the nav."""
    return {"pending_count": Evaluation.objects.filter(decision="step_up", resolution="").count()}
