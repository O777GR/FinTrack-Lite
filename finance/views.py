from django.views.generic import TemplateView, FormView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django import forms
import pandas as pd
import json
import os, tempfile
from decimal import Decimal
from collections import defaultdict
from django.db import models as django_models
from .models import Transaction, Category, Budget, FinancialGoal, Account
from .forms import CSVImportForm, TransactionForm
from .charts import Chart
from .utils import import_bank_csv, import_bank_csv_from_df
from .forecast import generate_forecast_report, get_forecast_chart_data


class DecimalEncoder(json.JSONEncoder):
    """Кастомный JSON encoder для Decimal"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (pd.Timestamp, pd.Period)):
            return str(obj)
        return super().default(obj)


def group_transactions_by_description(transactions):
    """Группирует транзакции по описанию и считает агрегаты."""
    groups = defaultdict(lambda: {
        'transactions': [],
        'category': None,
        'total_income': 0.0,
        'total_expense': 0.0,
        'first_date': None,
        'last_date': None,
    })
    
    for tx in transactions:
        key = tx.description or '—'
        group = groups[key]
        
        group['transactions'].append(tx)
        if group['category'] is None:
            group['category'] = tx.category
        
        amount = float(tx.amount)
        if tx.is_income:
            group['total_income'] += amount
        else:
            group['total_expense'] += amount
        
        if group['last_date'] is None:
            group['last_date'] = tx.date
        group['first_date'] = tx.date
    
    result = []
    for description, data in groups.items():
        result.append({
            'description': description,
            'category': data['category'],
            'transactions': data['transactions'],
            'count': len(data['transactions']),
            'total_income': data['total_income'],
            'total_expense': data['total_expense'],
            'total_net': data['total_income'] - data['total_expense'],
            'is_income': data['total_income'] >= data['total_expense'],
            'first_date': data['first_date'],
            'last_date': data['last_date'],
        })
    
    result.sort(key=lambda x: x['last_date'], reverse=True)
    return result


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'finance/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        qs = Transaction.objects.filter(user=user).select_related('category')
        
        if qs.exists():
            df = pd.DataFrame(list(qs.values(
                'id', 'amount', 'transaction_type', 'date',
                'category__name', 'category__color', 'description', 'goal', 'account'
            )))
            
            df['date'] = pd.to_datetime(df['date'])
            df['month'] = df['date'].dt.to_period('M').astype(str)
            
            # Исключаем из расходов переводы на цели И на счета
            expense_qs = df[
                (df['transaction_type']=='expense') & 
                (df['goal'].isna()) & 
                (df['account'].isna())
            ]
            income = float(df[df['transaction_type']=='income']['amount'].sum())
            expense = float(expense_qs['amount'].sum()) if not expense_qs.empty else 0
            months = df['month'].nunique() or 1
            
            context['kpi'] = {
                'balance': round(income - expense, 2),
                'income': round(income, 2),
                'expense': round(expense, 2),
                'avg': round(expense / months, 2),
            }
            
            charts = []
            
            monthly_data = df.groupby(['month', 'transaction_type'])['amount'].sum().unstack(fill_value=0)
            if not monthly_data.empty:
                chart = Chart('bar', 'monthly_flow')
                data = {
                    'labels': [str(m) for m in monthly_data.index],
                    'datasets': [
                        {
                            'label': 'Доходы', 
                            'data': [float(x) for x in (monthly_data['income'].tolist() if 'income' in monthly_data.columns else [])], 
                            'backgroundColor': '#2ecc71'
                        },
                        {
                            'label': 'Расходы', 
                            'data': [float(x) for x in (monthly_data['expense'].tolist() if 'expense' in monthly_data.columns else [])], 
                            'backgroundColor': '#e74c3c'
                        }
                    ]
                }
                config = chart.to_json_config(data, '📊 Доходы/Расходы по месяцам')
                charts.append({
                    'html': f'<canvas id="{chart.chart_id}"></canvas>',
                    'data_json': json.dumps(config, cls=DecimalEncoder),
                    'title': 'Доходы/Расходы',
                    'chart_id': chart.chart_id
                })
            
            expense_df = df[
                (df['transaction_type']=='expense') & 
                (df['goal'].isna()) & 
                (df['account'].isna())
            ]
            if not expense_df.empty:
                cat_data = expense_df.groupby('category__name')['amount'].sum().sort_values(ascending=False)
                chart = Chart('doughnut', 'categories_pie')
                data = {
                    'labels': [str(c) for c in cat_data.index],
                    'datasets': [
                        {
                            'data': [float(x) for x in cat_data.tolist()], 
                            'backgroundColor': chart.palette[:len(cat_data)]
                        }
                    ]
                }
                config = chart.to_json_config(data, '🥧 Расходы по категориям')
                charts.append({
                    'html': f'<canvas id="{chart.chart_id}"></canvas>',
                    'data_json': json.dumps(config, cls=DecimalEncoder),
                    'title': 'Категории',
                    'chart_id': chart.chart_id
                })
            
            forecast_report = generate_forecast_report(qs)
            context['forecast'] = forecast_report
            
            if forecast_report['total_forecast'] > 0:
                forecast_chart_data = get_forecast_chart_data(forecast_report)
                forecast_chart = Chart('bar', 'forecast_chart')
                forecast_config = forecast_chart.to_json_config(
                    forecast_chart_data, 
                    '🤖 Прогноз расходов на следующий месяц'
                )
                charts.append({
                    'html': f'<canvas id="{forecast_chart.chart_id}"></canvas>',
                    'data_json': json.dumps(forecast_config, cls=DecimalEncoder),
                    'title': 'Прогноз расходов',
                    'chart_id': forecast_chart.chart_id
                })
            
            context['charts'] = charts
        else:
            context['kpi'] = {'balance': 0, 'income': 0, 'expense': 0, 'avg': 0}
            context['charts'] = []
            context['forecast'] = {'total_forecast': 0.0, 'categories': []}
        
        context['transaction_form'] = TransactionForm(user=user)
        return context


class CSVImportView(LoginRequiredMixin, FormView):
    template_name = 'finance/import.html'
    form_class = CSVImportForm
    success_url = reverse_lazy('finance:dashboard')

    def form_valid(self, form):
        f = form.cleaned_data['csv_file']
        ext = f.name.split('.')[-1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp:
            for chunk in f.chunks(): tmp.write(chunk)
            path = tmp.name
        try:
            if ext == 'pdf':
                from .sberbank_pdf_parser import parse_sberbank_pdf
                df = parse_sberbank_pdf(path)
                stats = import_bank_csv_from_df(df, self.request.user.id)
            else:
                stats = import_bank_csv(path, self.request.user.id)
            messages.success(self.request, f"✅ Загружено: {stats['created']}, пропущено: {stats['skipped']}, ошибок: {stats['errors']}")
        except Exception as e:
            messages.error(self.request, f"❌ Ошибка: {e}")
        finally:
            try: os.unlink(path)
            except: pass
        return super().form_valid(form)


class TransactionsListView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = 'finance/transactions.html'
    context_object_name = 'transactions'
    paginate_by = 50
    
    def get_queryset(self):
        qs = Transaction.objects.filter(user=self.request.user)
        
        if category := self.request.GET.get('category'):
            qs = qs.filter(category_id=category)
        if tx_type := self.request.GET.get('type'):
            qs = qs.filter(transaction_type=tx_type)
        if date_from := self.request.GET.get('date_from'):
            qs = qs.filter(date__gte=date_from)
        if date_to := self.request.GET.get('date_to'):
            qs = qs.filter(date__lte=date_to)
        
        return qs.select_related('category').order_by('-date')
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = Category.objects.filter(
            user=self.request.user, is_active=True
        )
        ctx['current_filters'] = {
            'category': self.request.GET.get('category', ''),
            'type': self.request.GET.get('type', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
        }
        ctx['group_by_desc'] = self.request.GET.get('group_by') == '1'
        
        if ctx['group_by_desc']:
            current_qs = self.get_queryset()
            ctx['grouped_transactions'] = group_transactions_by_description(list(current_qs))
        
        return ctx


class GoalsView(LoginRequiredMixin, TemplateView):
    template_name = 'finance/goals.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        goals = FinancialGoal.objects.filter(user=user, is_active=True)
        
        for goal in goals:
            total = Transaction.objects.filter(
                user=user,
                goal=goal,
                transaction_type='expense'
            ).aggregate(total=django_models.Sum('amount'))['total'] or 0
            goal.current_amount = total
            goal.save()
        
        goals_with_history = []
        for goal in goals:
            history = list(
                goal.history.values('date', 'amount')
                .order_by('date')
            )
            goals_with_history.append({
                'goal': goal,
                'history': history
            })
        
        total_saved = sum(float(g.current_amount) for g in goals)
        total_target = sum(float(g.target_amount) for g in goals)
        
        context['goals'] = goals
        context['goals_with_history'] = goals_with_history
        context['total_saved'] = round(total_saved, 2)
        context['total_target'] = round(total_target, 2)
        context['total_progress'] = round(total_saved / total_target * 100, 1) if total_target > 0 else 0
        
        return context


class AccountsView(LoginRequiredMixin, TemplateView):
    template_name = 'finance/accounts.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        accounts = Account.objects.filter(user=user, is_active=True)
        
        accounts_by_type = {}
        for acc in accounts:
            acc_type = acc.get_account_type_display()
            if acc_type not in accounts_by_type:
                accounts_by_type[acc_type] = []
            accounts_by_type[acc_type].append(acc)
        
        total_assets = sum(float(acc.balance) for acc in accounts)
        
        context['accounts'] = accounts
        context['accounts_by_type'] = accounts_by_type
        context['total_assets'] = round(total_assets, 2)
        
        return context


class BindTransactionForm(forms.Form):
    transaction_ids = forms.CharField(widget=forms.HiddenInput())
    goal = forms.ModelChoiceField(
        queryset=FinancialGoal.objects.none(),
        required=False,
        label="Финансовая цель"
    )
    account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        required=False,
        label="Счёт"
    )


class BindTransactionsView(LoginRequiredMixin, FormView):
    template_name = 'finance/bind_transactions.html'
    form_class = BindTransactionForm
    success_url = '/finance/bind-transactions/'
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['goal'].queryset = FinancialGoal.objects.filter(
            user=self.request.user, is_active=True
        )
        form.fields['account'].queryset = Account.objects.filter(
            user=self.request.user, is_active=True
        )
        return form
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Получаем ВСЕ транзакции без цели и без счёта
        unbound_transactions = list(
            Transaction.objects.filter(
                user=self.request.user,
                goal__isnull=True,
                account__isnull=True
            )
            .select_related('category')
            .order_by('description', '-date')
        )
        
        # Группируем на стороне Python с правильным подсчётом суммы
        grouped = defaultdict(lambda: {
            'transactions': [],
            'total_sum': 0.0,
            'count': 0,
            'is_income': True,
        })
        
        for tx in unbound_transactions:
            key = tx.description or 'Без описания'
            group = grouped[key]
            group['transactions'].append(tx)
            group['count'] += 1
            
            amount = float(tx.amount)
            if tx.is_income:
                group['total_sum'] += amount
            else:
                group['total_sum'] -= amount
                group['is_income'] = False
        
        # Превращаем в список для шаблона
        grouped_list = []
        for description, data in grouped.items():
            grouped_list.append({
                'description': description,
                'transactions': data['transactions'],
                'total_sum': round(data['total_sum'], 2),
                'count': data['count'],
                'is_income': data['is_income'],
            })
        
        # Сортируем по дате последней транзакции (новые сверху)
        grouped_list.sort(
            key=lambda x: x['transactions'][0].date if x['transactions'] else None,
            reverse=True
        )
        
        context['grouped_transactions'] = grouped_list
        context['total_unbound'] = len(unbound_transactions)
        return context
    
    def form_valid(self, form):
        transaction_ids = form.cleaned_data['transaction_ids'].split(',')
        goal = form.cleaned_data.get('goal')
        account = form.cleaned_data.get('account')
        
        updated = 0
        for tx_id in transaction_ids:
            try:
                tx = Transaction.objects.get(
                    id=int(tx_id),
                    user=self.request.user
                )
                if goal:
                    tx.goal = goal
                if account:
                    tx.account = account
                tx.save()
                updated += 1
            except (Transaction.DoesNotExist, ValueError):
                pass
        
        messages.success(self.request, f"✅ Привязано {updated} транзакций")
        return super().form_valid(form)