import pdfplumber
import re
import pandas as pd
from .models import FinancialGoal


def parse_sberbank_pdf(pdf_path: str) -> pd.DataFrame:
    """
    Парсер PDF выписки Сбербанка.
    Использует строгое регулярное выражение для точного извлечения данных.
    """
    transactions = []
    
    pattern = re.compile(
        r"(\d{2}\.\d{2}\.\d{4})\s+"
        r"(\d{2}:\d{2})\s+"
        r"(.+?)\s+"
        r"([+-]?\s*\d{1,3}(?:\s\d{3})*[,.]\d{2})\s+"
        r"(\d{2}\.\d{2}\.\d{4})\s+"
        r"(\d{6})\s+"
        r"(.+?)\s+"
        r"Операция по карте"
    )

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            
            for match in pattern.finditer(text):
                date_str = match.group(1)
                category = match.group(3).strip()
                amount_raw = match.group(4).strip()
                description_raw = match.group(7).strip()
                
                is_income = '+' in amount_raw
                transaction_type = 'income' if is_income else 'expense'
                amount_val = float(amount_raw.replace(' ', '').replace(',', '.').replace('+', ''))
                
                description = description_raw.replace('Операция по карте', '').strip()
                description = description.replace('****6690', '').strip()
                
                # 🔧 АВТО-ОПРЕДЕЛЕНИЕ ФИНАНСОВОЙ ЦЕЛИ
                goal = auto_detect_goal(description, transaction_type)
                
                transactions.append({
                    'date': date_str,
                    'category': category,
                    'description': description[:200],
                    'amount': amount_val,
                    'transaction_type': transaction_type,
                    'goal': goal
                })

    if not transactions:
        raise ValueError("Не найдено транзакций в PDF")
    
    df = pd.DataFrame(transactions)
    df['date'] = pd.to_datetime(df['date'], dayfirst=True).dt.strftime('%Y-%m-%d')
    
    return df[['date', 'amount', 'description', 'category', 'transaction_type', 'goal']]


def auto_detect_goal(description: str, transaction_type: str) -> int:
    """
    Автоматически определяет финансовую цель по описанию транзакции.
    Возвращает ID цели или None.
    """
    if transaction_type != 'expense':
        return None
    
    description_lower = description.lower()
    
    # Ключевые слова для определения целей
    goal_keywords = {
        'инвестиц': 'investment',
        'инвестиция': 'investment',
        'брокер': 'investment',
        'биржа': 'investment',
        'акции': 'investment',
        'облигации': 'investment',
        'иис': 'investment',
        
        'вклад': 'deposit',
        'депозит': 'deposit',
        'накопительный': 'deposit',
        'сберегательный': 'deposit',
        
        'подушка': 'savings',
        'сбереж': 'savings',
        'накоплен': 'savings',
        'резерв': 'savings',
        'нз': 'savings',  # неприкосновенный запас
    }
    
    # Ищем совпадения
    for keyword, goal_type in goal_keywords.items():
        if keyword in description_lower:
            # Находим цель по типу
            goal = find_goal_by_type(goal_type)
            if goal:
                return goal.id
    
    return None


def find_goal_by_type(goal_type: str):
    """Находит активную цель по типу."""
    from .models import FinancialGoal
    
    # Имена целей для каждого типа (можно настроить под себя)
    type_names = {
        'investment': ['Инвестиц', 'Инвестиционный', 'Портфель'],
        'deposit': ['Вклад', 'Депозит', 'Сбербанк'],
        'savings': ['Подушка', 'Сбереж', 'Накоплен', 'Резерв'],
    }
    
    names = type_names.get(goal_type, [])
    
    # Ищем цель, у которой в названии есть ключевые слова
    for name in names:
        goal = FinancialGoal.objects.filter(
            name__icontains=name,
            is_active=True
        ).first()
        if goal:
            return goal
    
    return None