from django.urls import path

from .views import (
    ApproveWorkView,
    HealthView,
    RequestRevisionView,
    ReviewDetailView,
    ReviewListCreateView,
    SubmitWorkView,
    WorkDetailView,
    WorkListCreateView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("work/", WorkListCreateView.as_view(), name="work-list-create"),
    path("work/<uuid:work_id>/", WorkDetailView.as_view(), name="work-detail"),
    path("work/<uuid:work_id>/submit/", SubmitWorkView.as_view(), name="work-submit"),
    path("work/<uuid:work_id>/reject/",RequestRevisionView.as_view(),name="work-reject",),
    path("work/<uuid:work_id>/approve/",ApproveWorkView.as_view(),name="work-approve",),
    path("reviews/",ReviewListCreateView.as_view(),name="review-list-create",),
    path("reviews/<uuid:review_id>/",ReviewDetailView.as_view(),name="review-detail",),
]
