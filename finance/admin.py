from django.contrib import admin
from .models import Category, Transaction, Budget

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "color", "is_active", "get_transactions_count")
    list_filter = ("is_active", "user")
    search_fields = ("name",)
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            return qs.filter(user=request.user)
        return qs

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "category", "transaction_type", "amount", "description")
    list_filter = ("transaction_type", "category", "date")
    search_fields = ("description", "user__username")
    date_hierarchy = "date"
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-date",)

@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "month", "limit", "get_spent", "is_over_budget")
    list_filter = ("month", "category")
    date_hierarchy = "month"
    readonly_fields = ("created_at",)