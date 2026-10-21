from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("projects.urls")),
]

# JSON error envelopes for bad requests, unknown routes and server errors.
handler400 = "projects.api.json_400"
handler404 = "projects.api.json_404"
handler500 = "projects.api.json_500"
