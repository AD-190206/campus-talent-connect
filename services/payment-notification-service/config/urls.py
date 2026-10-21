from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("payments_notifications.urls")),
]

# JSON error envelopes for unknown routes and server errors.
handler404 = "payments_notifications.exceptions.json_404"
handler500 = "payments_notifications.exceptions.json_500"
