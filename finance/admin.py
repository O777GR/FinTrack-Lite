from django.contrib import admin
from .models import Transaction, Category, Budget, FinancialGoal, FinancialGoalHistory, Account


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'color', 'is_active', 'user']
    list_filter = ['is_active', 'user']
    search_fields = ['name']
    list_editable = ['is_active']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'date', 'amount', 'transaction_type', 'category', 'goal', 'description', 'user']
    list_filter = ['transaction_type', 'category', 'goal', 'date', 'user']
    search_fields = ['description']
    date_hierarchy = 'date'
    raw_id_fields = ['user', 'category', 'goal']
    list_per_page = 50


@admin.register(FinancialGoal)
class FinancialGoalAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'target_amount', 'current_amount', 'progress_percent', 'is_active', 'user']
    list_filter = ['is_active', 'user']
    search_fields = ['name', 'description']
    readonly_fields = ['current_amount']


@admin.register(FinancialGoalHistory)
class FinancialGoalHistoryAdmin(admin.ModelAdmin):
    list_display = ['goal', 'date', 'amount', 'note', 'created_at']
    list_filter = ['goal', 'date']
    readonly_fields = ['created_at']


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'account_type', 'balance', 'currency', 'is_active', 'user']
    list_filter = ['account_type', 'is_active', 'user']
    search_fields = ['name', 'description']
    list_editable = ['is_active']


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'category', 'amount', 'month']
    list_filter = ['user', 'category', 'month']
    raw_id_fields = ['user', 'category']