
from django.contrib import admin
from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "client_id",
        "status",
        "budget",
        "deadline",
        "created_at",
    )
    list_filter = ("status", "category")
    search_fields = ("title", "description", "client_id")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("-created_at",)
