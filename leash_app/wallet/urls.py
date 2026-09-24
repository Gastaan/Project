from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # policies
    path("policies/", views.policy_list, name="policy_list"),
    path("policies/add/", views.policy_add, name="policy_add"),
    path("policies/preset/", views.policy_load_preset, name="policy_load_preset"),
    path("policies/<int:pk>/edit/", views.policy_edit, name="policy_edit"),
    path("policies/<int:pk>/toggle/", views.policy_toggle, name="policy_toggle"),
    path("policies/<int:pk>/delete/", views.policy_delete, name="policy_delete"),
    # history
    path("history/", views.history_list, name="history_list"),
    path("history/<int:pk>/", views.history_detail, name="history_detail"),
    # evaluate
    path("try/", views.try_page, name="try_page"),
    path("api/evaluate", views.api_evaluate, name="api_evaluate"),
    # live Leash API
    path("connector/", views.connector_panel, name="connector_panel"),
    path("connector/mandates/draft/", views.mandate_draft, name="mandate_draft"),
    path("connector/mandates/<int:pk>/confirm/", views.mandate_confirm, name="mandate_confirm"),
    path("connector/mandates/<int:pk>/revoke/", views.mandate_revoke, name="mandate_revoke"),
    path("connector/mandates/<int:pk>/run/", views.run_start, name="run_start"),
    path("connector/runs/<int:pk>/refresh/", views.run_refresh, name="run_refresh"),
    path("connector/resolve/<int:pk>/", views.resolve, name="resolve"),
]
