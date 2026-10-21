from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("work_review.urls")),
]

# JSON error envelopes for unknown routes and server errors.
handler404 = "work_review.exceptions.json_404"
handler500 = "work_review.exceptions.json_500"
