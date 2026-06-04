from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('import/', views.CSVImportView.as_view(), name='import'),
    path('transactions/', views.TransactionsListView.as_view(), name='transactions'),
    path('goals/', views.GoalsView.as_view(), name='goals'),
    path('accounts/', views.AccountsView.as_view(), name='accounts'),
    path('bind-transactions/', views.BindTransactionsView.as_view(), name='bind_transactions'),
]