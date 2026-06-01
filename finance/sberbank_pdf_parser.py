import pdfplumber
import re
import pandas as pd


def parse_sberbank_pdf(pdf_path: str) -> pd.DataFrame:
    """
    Парсер PDF выписки Сбербанка.
    Использует строгое регулярное выражение для точного извлечения данных
    из единой строки транзакции.
    """
    transactions = []
    
    # Регулярное выражение охватывает всю структуру транзакции Сбера:
    # 1. Дата1 (ДД.ММ.ГГГГ) 2. Время (ЧЧ:ММ) 3. Категория 4. Сумма
    # 5. Дата2 (ДД.ММ.ГГГГ) 6. Код (6 цифр) 7. Описание (до "Операция по карте")
    pattern = re.compile(
        r"(\d{2}\.\d{2}\.\d{4})\s+"           # Группа 1: Дата операции
        r"(\d{2}:\d{2})\s+"                    # Группа 2: Время
        r"(.+?)\s+"                            # Группа 3: Категория (ленивый поиск)
        r"([+-]?\s*\d{1,3}(?:\s\d{3})*[,.]\d{2})\s+" # Группа 4: Сумма (с учетом знака + и пробелов)
        r"(\d{2}\.\d{2}\.\d{4})\s+"            # Группа 5: Дата обработки
        r"(\d{6})\s+"                          # Группа 6: Код авторизации
        r"(.+?)\s+"                            # Группа 7: Описание (до конца)
        r"Операция по карте"                   # Фиксированный конец
    )

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            
            # Ищем все совпадения в тексте страницы
            for match in pattern.finditer(text):
                date_str = match.group(1)
                category = match.group(3).strip()
                amount_raw = match.group(4).strip()
                description_raw = match.group(7).strip()
                
                # Определяем тип операции по знаку +
                is_income = '+' in amount_raw
                transaction_type = 'income' if is_income else 'expense'
                
                # Очищаем сумму
                amount_val = float(amount_raw.replace(' ', '').replace(',', '.').replace('+', ''))
                
                # Очищаем описание
                description = description_raw.replace('Операция по карте', '').strip()
                description = description.replace('****6690', '').strip()
                
                transactions.append({
                    'date': date_str,
                    'category': category,
                    'description': description[:200],
                    'amount': amount_val,
                    'transaction_type': transaction_type
                })

    if not transactions:
        raise ValueError("Не найдено транзакций в PDF. Проверьте формат файла.")
    
    df = pd.DataFrame(transactions)
    print(f"✅ Найдено транзакций: {len(df)}")
    print(f"📊 Доходы: {len(df[df['transaction_type']=='income'])}")
    print(f"📊 Расходы: {len(df[df['transaction_type']=='expense'])}")
    print(f"\n📋 Примеры описаний:")
    # Показываем переводы, чтобы убедиться, что имена на месте
    transfers = df[df['category'].str.contains('Перевод')]
    if not transfers.empty:
        print(transfers[['date', 'description']].head())
    
    # Конвертируем даты
    df['date'] = pd.to_datetime(df['date'], dayfirst=True).dt.strftime('%Y-%m-%d')
    
    return df[['date', 'amount', 'description', 'category', 'transaction_type']]