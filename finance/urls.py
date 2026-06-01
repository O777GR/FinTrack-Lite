"""
URL patterns for finance app.
"""
from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('import/', views.CSVImportView.as_view(), name='import'),
    path('transactions/', views.TransactionsListView.as_view(), name='transactions'),
]