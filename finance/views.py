from django.views.generic import TemplateView, FormView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
import pandas as pd
import json
import os, tempfile
from decimal import Decimal
from collections import defaultdict
from .models import Transaction, Category, Budget
from .forms import CSVImportForm, TransactionForm
from .charts import Chart
from .utils import import_bank_csv, import_bank_csv_from_df, CSVImportError
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
                'category__name', 'category__color', 'description'
            )))
            
            df['date'] = pd.to_datetime(df['date'])
            df['month'] = df['date'].dt.to_period('M').astype(str)
            
            income = float(df[df['transaction_type']=='income']['amount'].sum())
            expense = float(df[df['transaction_type']=='expense']['amount'].sum())
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
            
            expense_df = df[df['transaction_type']=='expense']
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
    """Список транзакций с фильтрацией и группировкой."""
    model = Transaction
    template_name = 'finance/transactions.html'
    context_object_name = 'transactions'
    paginate_by = 50
    
    def get_queryset(self):
        print("="*60)
        print("DEBUG TransactionsListView: get_queryset")
        print("="*60)
        
        user = self.request.user
        print(f"DEBUG: Пользователь: {user.username} (ID: {user.id})")
        
        # 🔧 Получаем ВСЕ транзакции пользователя
        qs = Transaction.objects.filter(user=user)
        total = qs.count()
        print(f"DEBUG: Всего транзакций в БД для этого пользователя: {total}")
        
        # Применяем фильтры
        if category := self.request.GET.get('category'):
            print(f"DEBUG: Фильтр по категории: {category}")
            qs = qs.filter(category_id=category)
        
        if tx_type := self.request.GET.get('type'):
            print(f"DEBUG: Фильтр по типу: {tx_type}")
            qs = qs.filter(transaction_type=tx_type)
        
        if date_from := self.request.GET.get('date_from'):
            print(f"DEBUG: Фильтр с даты: {date_from}")
            qs = qs.filter(date__gte=date_from)
        
        if date_to := self.request.GET.get('date_to'):
            print(f"DEBUG: Фильтр по дату: {date_to}")
            qs = qs.filter(date__lte=date_to)
        
        final_count = qs.count()
        print(f"DEBUG: После фильтров осталось: {final_count} транзакций")
        
        # Сортируем и добавляем select_related
        qs = qs.select_related('category').order_by('-date')
        
        print("="*60)
        return qs
    
    def get_context_data(self, **kwargs):
        print("DEBUG TransactionsListView: get_context_data")
        
        ctx = super().get_context_data(**kwargs)
        
        # Категории
        ctx['categories'] = Category.objects.filter(
            user=self.request.user, is_active=True
        )
        print(f"DEBUG: Категорий: {ctx['categories'].count()}")
        
        # Текущие фильтры
        ctx['current_filters'] = {
            'category': self.request.GET.get('category', ''),
            'type': self.request.GET.get('type', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
        }
        
        # Режим группировки
        ctx['group_by_desc'] = self.request.GET.get('group_by') == '1'
        print(f"DEBUG: Группировка: {ctx['group_by_desc']}")
        
        # Транзакции
        transactions = ctx['transactions']
        print(f"DEBUG: Транзакций в контексте: {len(transactions)}")
        
        if transactions:
            print(f"DEBUG: Первая транзакция: {transactions[0]}")
        
        # Группировка если включена
        if ctx['group_by_desc']:
            current_qs = self.get_queryset()
            grouped = group_transactions_by_description(list(current_qs))
            ctx['grouped_transactions'] = grouped
            print(f"DEBUG: Сгруппировано в {len(grouped)} групп")
        
        print("="*60)
        return ctx