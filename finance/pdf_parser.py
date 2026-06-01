"""
Парсер PDF выписок Сбербанка.
Extracts transactions from Sberbank PDF statements.
"""
import pdfplumber
import pandas as pd
import re
from datetime import datetime
from typing import List, Dict


def parse_sberbank_pdf(pdf_path: str) -> pd.DataFrame:
    """
    Извлекает транзакции из PDF выписки Сбербанка.
    
    Args:
        pdf_path: Путь к PDF файлу
        
    Returns:
        DataFrame с колонками: date, category, description, amount
    """
    transactions = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
                
            # Разбиваем текст на строки
            lines = text.split('\n')
            
            for line in lines:
                # Пропускаем служебные строки
                if any(skip in line for skip in [
                    'ДАТА ОПЕРАЦИИ', 'ИТОГО ПО ОПЕРАЦИЯМ', 
                    'Продолжение на следующей', 'Страница',
                    'Владелец счёта', 'Номер счёта'
                ]):
                    continue
                
                # Паттерн для поиска транзакций
                # Формат: ДАТА КАТЕГОРИЯ СУММА ОПИСАНИЕ
                # Пример: 31.05.2026 11:09 Супермаркеты 134,97 PYATEROCHKA...
                
                # Ищем дату в начале строки
                date_match = re.match(r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})?', line)
                if not date_match:
                    continue
                
                date_str = date_match.group(1)
                
                # Ищем сумму (может быть с + или без)
                # Паттерн: число с запятой или точкой, возможно со знаком +
                amount_match = re.search(r'([+-]?\s*\d{1,3}(?:\s\d{3})*[,.]\d{2})', line)
                if not amount_match:
                    continue
                
                amount_str = amount_match.group(1).replace(' ', '').replace(',', '.')
                
                # Определяем категорию (слова после даты и времени)
                # Категории Сбера
                categories = [
                    'Супермаркеты', 'Перевод на карту', 'Здоровье и красота',
                    'Транспорт', 'Отдых и развлечения', 'Одежда и аксессуары',
                    'Все для дома', 'Прочие операции', 'Перевод СБП',
                    'Перевод с карты', 'Оплата по QR–коду СБП'
                ]
                
                category = 'Прочие операции'
                for cat in categories:
                    if cat in line:
                        category = cat
                        break
                
                # Извлекаем описание (всё после суммы)
                desc_start = amount_match.end()
                description = line[desc_start:].strip()
                
                # Очищаем описание от лишних символов
                description = re.sub(r'\s+', ' ', description)
                
                # Пропускаем если описание слишком короткое
                if len(description) < 5:
                    continue
                
                transactions.append({
                    'date': date_str,
                    'category': category,
                    'description': description[:200],  # Ограничиваем длину
                    'amount': amount_str
                })
    
    if not transactions:
        raise ValueError("Не удалось найти транзакции в PDF. Проверьте формат файла.")
    
    df = pd.DataFrame(transactions)
    print(f"✅ Найдено транзакций: {len(df)}")
    print(f"📊 Распределение по категориям:\n{df['category'].value_counts()}")
    
    return df


def convert_pdf_to_csv(pdf_path: str, csv_path: str) -> None:
    """
    Конвертирует PDF выписку в CSV формат.
    
    Args:
        pdf_path: Путь к PDF файлу
        csv_path: Путь для сохранения CSV
    """
    df = parse_sberbank_pdf(pdf_path)
    df.to_csv(csv_path, index=False, sep=';', encoding='utf-8-sig')
    print(f"💾 CSV сохранён: {csv_path}")


if __name__ == '__main__':
    # Пример использования
    import sys
    
    if len(sys.argv) < 2:
        print("Использование: python pdf_parser.py <path_to_pdf>")
        sys.exit(1)
    
    pdf_file = sys.argv[1]
    csv_file = pdf_file.replace('.pdf', '.csv')
    
    try:
        convert_pdf_to_csv(pdf_file, csv_file)
        print("\n✅ Готово! Теперь загрузите CSV через /finance/import/")
    except Exception as e:
        print(f"❌ Ошибка: {e}")