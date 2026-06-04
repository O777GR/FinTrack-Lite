"""
Модуль прогнозирования расходов на основе истории транзакций.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List
from decimal import Decimal


def calculate_monthly_expenses(transactions_qs) -> pd.DataFrame:
    """
    Агрегирует расходы по месяцам и категориям.
    """
    data = list(transactions_qs.filter(
        transaction_type='expense'
    ).values('date', 'amount', 'category__name'))
    
    if not data:
        return pd.DataFrame()
    
    df = pd.DataFrame(data)
    
    if df.empty:
        return pd.DataFrame()
    
    # Преобразуем Decimal в float
    df['amount'] = df['amount'].apply(lambda x: float(x) if isinstance(x, Decimal) else float(x))
    
    # Преобразуем даты
    df['date'] = pd.to_datetime(df['date'])
    df['month'] = df['date'].dt.to_period('M')
    
    # Группируем по месяцу и категории
    monthly = df.groupby(['month', 'category__name'])['amount'].sum().reset_index()
    monthly.columns = ['month', 'category', 'amount']
    
    return monthly


def forecast_next_month(monthly_df: pd.DataFrame, category: str) -> Dict:
    """
    Прогнозирует расходы на следующий месяц для конкретной категории.
    """
    cat_data = monthly_df[monthly_df['category'] == category].copy()
    
    if cat_data.empty:
        return {
            'category': category,
            'forecast': 0.0,
            'confidence': 'low',
            'trend': 'insufficient_data',
            'history': []
        }
    
    # Сортируем по времени
    cat_data = cat_data.sort_values('month')
    
    # История расходов
    history = []
    for _, row in cat_data.iterrows():
        history.append({
            'month': str(row['month']),
            'amount': float(row['amount'])
        })
    
    # 🔧 ИСПРАВЛЕНИЕ: Прогнозирование работает даже с 1 месяцем данных
    if len(cat_data) >= 3:
        # Много данных: взвешенное скользящее среднее
        recent_3 = cat_data.tail(3)['amount'].mean()
        recent_6 = cat_data.tail(6)['amount'].mean() if len(cat_data) >= 6 else recent_3
        forecast = (recent_3 * 0.7 + recent_6 * 0.3)
        confidence = 'high' if len(cat_data) >= 6 else 'medium'
    elif len(cat_data) == 2:
        # 2 месяца: простое среднее
        forecast = cat_data['amount'].mean()
        confidence = 'low'
    else:
        # 1 месяц: используем фактические данные как прогноз
        forecast = cat_data['amount'].iloc[0]
        confidence = 'low'
    
    # Определяем тренд
    if len(cat_data) >= 3:
        last_3_avg = cat_data.tail(3)['amount'].mean()
        prev_3_avg = cat_data.head(3)['amount'].mean()
        
        if last_3_avg > prev_3_avg * 1.1:
            trend = 'increasing'
        elif last_3_avg < prev_3_avg * 0.9:
            trend = 'decreasing'
        else:
            trend = 'stable'
    else:
        trend = 'insufficient_data'
    
    return {
        'category': category,
        'forecast': round(float(forecast), 2),
        'confidence': confidence,
        'trend': trend,
        'history': history
    }


def generate_forecast_report(transactions_qs) -> Dict:
    """
    Генерирует полный отчёт по прогнозированию расходов.
    """
    print("DEBUG forecast: Начинаем генерацию отчёта...")
    
    monthly_df = calculate_monthly_expenses(transactions_qs)
    
    print(f"DEBUG forecast: monthly_df имеет {len(monthly_df)} строк")
    if not monthly_df.empty:
        print(f"DEBUG forecast: Категории: {monthly_df['category'].unique()}")
    
    if monthly_df.empty:
        return {
            'total_forecast': 0.0,
            'categories': [],
            'generated_at': datetime.now().isoformat()
        }
    
    # Получаем уникальные категории
    categories = monthly_df['category'].unique()
    print(f"DEBUG forecast: Найдено категорий: {len(categories)}")
    
    # Прогнозируем для каждой категории
    forecasts = []
    total_forecast = 0.0
    
    for category in categories:
        forecast = forecast_next_month(monthly_df, category)
        print(f"DEBUG forecast: {category} -> {forecast['forecast']} ₽ (confidence: {forecast['confidence']})")
        forecasts.append(forecast)
        total_forecast += forecast['forecast']
    
    # Сортируем по убыванию прогноза
    forecasts.sort(key=lambda x: x['forecast'], reverse=True)
    
    result = {
        'total_forecast': round(float(total_forecast), 2),
        'categories': forecasts,
        'generated_at': datetime.now().isoformat()
    }
    
    print(f"DEBUG forecast: Итоговый прогноз: {result['total_forecast']} ₽")
    
    return result


def get_forecast_chart_data(forecast_report: Dict) -> Dict:
    """
    Преобразует отчёт прогноза в формат для Chart.js.
    """
    categories = forecast_report['categories']
    
    if not categories:
        return {'labels': [], 'datasets': []}
    
    # Берём только категории с прогнозом > 0
    categories_with_forecast = [cat for cat in categories if cat['forecast'] > 0]
    
    if not categories_with_forecast:
        return {'labels': [], 'datasets': []}
    
    # Берём топ-10 категорий по прогнозу
    top_categories = categories_with_forecast[:10]
    
    labels = [cat['category'] for cat in top_categories]
    forecasts = [float(cat['forecast']) for cat in top_categories]
    
    print(f"DEBUG chart: labels={labels}")
    print(f"DEBUG chart: forecasts={forecasts}")
    
    # Цвета в зависимости от тренда
    colors = []
    for cat in top_categories:
        if cat['trend'] == 'increasing':
            colors.append('#e74c3c')  # Красный - растёт
        elif cat['trend'] == 'decreasing':
            colors.append('#2ecc71')  # Зелёный - падает
        else:
            colors.append('#3498db')  # Синий - стабильно
    
    return {
        'type': 'bar',
        'labels': labels,
        'datasets': [{
            'label': 'Прогноз на следующий месяц (₽)',
            'data': forecasts,
            'backgroundColor': colors,
            'borderColor': colors,
            'borderWidth': 1
        }]
    }