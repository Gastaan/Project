from django.urls import include, path

urlpatterns = [path("", include("wallet.urls"))]
