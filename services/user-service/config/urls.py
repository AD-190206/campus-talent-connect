from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("users.urls")),
]

# JSON error envelopes for unknown routes and server errors.
handler404 = "users.exceptions.json_404"
handler500 = "users.exceptions.json_500"
