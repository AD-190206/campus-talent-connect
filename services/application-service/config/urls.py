from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("applications.urls")),
]

# JSON error envelopes for unknown routes and server errors.
handler404 = "applications.api.json_404"
handler500 = "applications.api.json_500"
