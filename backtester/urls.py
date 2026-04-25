"""URL routes for backtest-as-a-service."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from runs.views import (
    rerun_run,
    rerun_sweep,
    run_detail,
    runs_list,
    sweep_detail,
    sweeps_list,
)


def health_check(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", TemplateView.as_view(template_name="landing.html"), name="landing"),
    path("runs/", runs_list, name="runs-page"),
    path("runs/<int:run_id>/", run_detail, name="run-detail"),
    path("runs/<int:run_id>/rerun/", rerun_run, name="run-rerun"),
    path("sweeps/", sweeps_list, name="sweeps-page"),
    path("sweeps/<int:sweep_id>/", sweep_detail, name="sweep-detail"),
    path("sweeps/<int:sweep_id>/rerun/", rerun_sweep, name="sweep-rerun"),
    path("admin/", admin.site.urls),
    path("healthz/", health_check, name="health-check"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/", include("runs.urls")),
]
