
from django.urls import path

from .views import (
    HealthView,
    PaymentListCreateView,
    PaymentDetailView,
    ProcessPaymentView,
    ReleasePaymentView,
    NotificationListCreateView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),

    path("payments/", PaymentListCreateView.as_view(), name="payment-list-create"),
    path("payments/history/", PaymentListCreateView.as_view(),
         name="payment-history"),
    path("payments/<uuid:payment_id>/",
         PaymentDetailView.as_view(), name="payment-detail"),
    path("payments/<uuid:payment_id>/process/",
         ProcessPaymentView.as_view(), name="payment-process"),
    path("payments/<uuid:payment_id>/release/",
         ReleasePaymentView.as_view(), name="payment-release"),

    path("notifications/", NotificationListCreateView.as_view(),
         name="notification-list-create"),
]
