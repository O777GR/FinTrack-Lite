import pandas as pd
from decimal import Decimal
from django.db import transaction
from .models import Transaction, Category
import random

class CSVImportError(Exception): pass

def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.lower().str.strip()
    df = df.rename(columns={
        'дата операции': 'date', 'дата': 'date', 'operation_date': 'date',
        'сумма': 'amount', 'sum': 'amount', 'value': 'amount',
        'описание': 'description', 'desc': 'description',
        'категория': 'category', 'cat': 'category',
    })
    df['date'] = pd.to_datetime(df['date'], errors='coerce', dayfirst=True).dt.date
    df = df.dropna(subset=['date'])
    df['amount'] = (df['amount'].astype(str).str.replace(r'[^\d.,\-]', '', regex=True)
                    .str.replace(',', '.', regex=False).pipe(pd.to_numeric, errors='coerce'))
    df = df.dropna(subset=['amount'])
    df['transaction_type'] = df['amount'].apply(lambda x: 'income' if x > 0 else 'expense')
    df['amount'] = df['amount'].abs().round(2)
    return df

def import_bank_csv(file_path: str, user_id: int) -> dict:
    stats = {'created': 0, 'skipped': 0, 'errors': 0}
    for encoding in ['cp1251', 'utf-8', 'utf-8-sig']:
        try:
            df = pd.read_csv(file_path, sep=';', encoding=encoding)
            break
        except UnicodeDecodeError: continue
    else:
        raise CSVImportError("Не удалось определить кодировку файла")
    
    df = normalize_dataframe(df)
    return import_bank_csv_from_df(df, user_id)

def import_bank_csv_from_df(df: pd.DataFrame, user_id: int) -> dict:
    """
    Импортирует транзакции из готового DataFrame.
    ВАЖНО: Использует transaction_type из DataFrame, а не вычисляет заново!
    """
    from .models import Transaction, Category
    import random
    
    stats = {'created': 0, 'skipped': 0, 'errors': 0}
    
    def random_color_hex() -> str:
        return f"{random.randint(0, 0xFFFFFF):06x}"
    
    with transaction.atomic():
        for _, row in df.iterrows():
            try:
                cat_key = row.get('category', 'other')
                
                category, _ = Category.objects.get_or_create(
                    name=cat_key, user_id=user_id,
                    defaults={'color': f"#{random_color_hex()}"}
                )
                
                # 🔧 ИСПРАВЛЕНИЕ: Берём amount как есть (уже с правильным знаком)
                amount_value = abs(Decimal(str(row['amount'])))
                
                # 🔧 ИСПРАВЛЕНИЕ: Берём transaction_type из DataFrame
                tx_type = row.get('transaction_type', 'expense')
                
                # Проверка на дубликаты
                exists = Transaction.objects.filter(
                    user_id=user_id,
                    date=row['date'],
                    amount=amount_value,
                    description=row.get('description', '')[:250]
                ).exists()
                
                if exists:
                    stats['skipped'] += 1
                    continue
                
                Transaction.objects.create(
                    user_id=user_id,
                    category=category,
                    amount=amount_value,
                    transaction_type=tx_type,  # Используем тип из DataFrame!
                    description=row.get('description', '')[:250],
                    date=row['date']
                )
                stats['created'] += 1
                
            except Exception as e:
                print(f"❌ Ошибка: {e}")
                stats['errors'] += 1
                continue
    
    return stats
    
    stats = {'created': 0, 'skipped': 0, 'errors': 0}
    with transaction.atomic():
        for _, row in df.iterrows():
            try:
                cat_key = row.get('category', 'other')
                category, _ = Category.objects.get_or_create(
                    name=cat_key, user_id=user_id,
                    defaults={'color': f"#{random.randint(0, 0xFFFFFF):06x}"}
                )
                if Transaction.objects.filter(user_id=user_id, date=row['date'], 
                                              amount=abs(Decimal(str(row['amount']))),
                                              description=row.get('description', '')[:250]).exists():
                    stats['skipped'] += 1; continue
                
                Transaction.objects.create(
                    user_id=user_id, category=category,
                    amount=abs(Decimal(str(row['amount']))),
                    transaction_type='income' if row['amount'] > 0 else 'expense',
                    description=row.get('description', '')[:250], date=row['date']
                )
                stats['created'] += 1
            except Exception:
                stats['errors'] += 1
    return stats