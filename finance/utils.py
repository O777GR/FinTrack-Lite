import pandas as pd
from .models import Transaction, Category
from decimal import Decimal
from datetime import datetime


def transaction_exists(date_str: str, amount: float, description: str, user_id: int) -> bool:
    """Проверяет, существует ли уже такая транзакция."""
    from django.utils import timezone
    
    # Парсим дату
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        return False
    
    # Ищем похожие транзакции
    existing = Transaction.objects.filter(
        user_id=user_id,
        date=date,
        amount=amount,
        description__icontains=description[:50] if len(description) > 50 else description
    ).exists()
    
    return existing


def import_bank_csv_from_df(df, user_id: int) -> dict:
    """
    Импортирует транзакции из DataFrame.
    Возвращает статистику.
    """
    from django.utils import timezone
    
    stats = {'created': 0, 'skipped': 0, 'errors': 0}
    
    for _, row in df.iterrows():
        try:
            # Проверяем на дубликат
            if transaction_exists(
                str(row['date']),
                float(row['amount']),
                str(row.get('description', '')),
                user_id
            ):
                stats['skipped'] += 1
                continue
            
            # Создаём транзакцию
            category = None
            category_name = row.get('category', '')
            if category_name:
                category, _ = Category.objects.get_or_create(
                    name=category_name,
                    defaults={'color': '#3498db'}
                )
            
            # Получаем goal из DataFrame (если авто-определение сработало)
            goal = None
            if 'goal' in row and pd.notna(row['goal']):
                try:
                    from .models import FinancialGoal
                    goal = FinancialGoal.objects.get(id=int(row['goal']))
                except:
                    pass
            
            Transaction.objects.create(
                user_id=user_id,
                date=row['date'],
                amount=row['amount'],
                description=row.get('description', ''),
                category=category,
                transaction_type=row['transaction_type'],
                goal=goal
            )
            stats['created'] += 1
            
        except Exception as e:
            print(f"Error importing row: {row}, error: {e}")
            stats['errors'] += 1
    
    return stats


def import_bank_csv(file_path: str, user_id: int) -> dict:
    """Импортирует транзакции из CSV файла."""
    import pandas as pd
    df = pd.read_csv(file_path)
    return import_bank_csv_from_df(df, user_id)