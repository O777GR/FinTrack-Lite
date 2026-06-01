from django.views.generic import TemplateView, FormView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
import pandas as pd
import json
import os, tempfile
from decimal import Decimal
from .models import Transaction, Category, Budget
from .forms import CSVImportForm, TransactionForm
from .charts import Chart
from .utils import import_bank_csv, import_bank_csv_from_df, CSVImportError


class DecimalEncoder(json.JSONEncoder):
    """Кастомный JSON encoder для Decimal"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (pd.Timestamp, pd.Period)):
            return str(obj)
        return super().default(obj)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'finance/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Получаем все транзакции
        qs = Transaction.objects.filter(user=user).select_related('category')
        
        if qs.exists():
            df = pd.DataFrame(list(qs.values(
                'id', 'amount', 'transaction_type', 'date',
                'category__name', 'category__color', 'description'
            )))
            
            # Преобразуем даты
            df['date'] = pd.to_datetime(df['date'])
            df['month'] = df['date'].dt.to_period('M').astype(str)
            
            # Рассчитываем KPI
            income = float(df[df['transaction_type']=='income']['amount'].sum())
            expense = float(df[df['transaction_type']=='expense']['amount'].sum())
            months = df['month'].nunique() or 1
            
            context['kpi'] = {
                'balance': round(income - expense, 2),
                'income': round(income, 2),
                'expense': round(expense, 2),
                'avg': round(expense / months, 2),
            }
            
            # Генерируем графики
            charts = []
            
            # 1. График доходов/расходов по месяцам
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
            
            # 2. График по категориям
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
            
            context['charts'] = charts
            print(f"DEBUG: Сгенерировано {len(charts)} графиков")
        else:
            context['kpi'] = {'balance': 0, 'income': 0, 'expense': 0, 'avg': 0}
            context['charts'] = []
        
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
        qs = super().get_queryset().filter(user=self.request.user)
        if c := self.request.GET.get('category'): qs = qs.filter(category_id=c)
        if t := self.request.GET.get('type'): qs = qs.filter(transaction_type=t)
        return qs.select_related('category').order_by('-date')
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = Category.objects.filter(user=self.request.user, is_active=True)
        return ctx