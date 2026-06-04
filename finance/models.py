from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Category(models.Model):
    """Категория транзакции"""
    name = models.CharField(max_length=100, unique=True)
    color = models.CharField(max_length=7, default='#3498db')
    icon = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class FinancialGoal(models.Model):
    """Финансовая цель (накопления, инвестиции, вклады)"""
    name = models.CharField("Название", max_length=100)
    description = models.TextField("Описание", blank=True)
    target_amount = models.DecimalField("Целевая сумма", max_digits=12, decimal_places=2)
    current_amount = models.DecimalField("Текущая сумма", max_digits=12, decimal_places=2, default=0)
    color = models.CharField("Цвет", max_length=7, default='#3498db')
    icon = models.CharField("Иконка (emoji)", max_length=10, default='💰')
    deadline = models.DateField("Срок", null=True, blank=True)
    is_active = models.BooleanField("Активна", default=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Финансовая цель"
        verbose_name_plural = "Финансовые цели"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.current_amount}/{self.target_amount} ₽)"
    
    def save(self, *args, **kwargs):
        """Автоматически создаёт запись истории при изменении current_amount"""
        if self.pk:
            try:
                old = FinancialGoal.objects.get(pk=self.pk)
                if old.current_amount != self.current_amount:
                    FinancialGoalHistory.objects.create(
                        goal=self,
                        date=timezone.now().date(),
                        amount=self.current_amount,
                        note="Автоматическое обновление"
                    )
            except FinancialGoal.DoesNotExist:
                pass
        super().save(*args, **kwargs)
    
    @property
    def progress_percent(self):
        """Процент выполнения"""
        if self.target_amount == 0:
            return 0
        return min(100, round(float(self.current_amount) / float(self.target_amount) * 100, 1))
    
    @property
    def remaining(self):
        """Осталось накопить"""
        return max(0, float(self.target_amount) - float(self.current_amount))


class FinancialGoalHistory(models.Model):
    """История изменений финансовых целей"""
    goal = models.ForeignKey(
        FinancialGoal, 
        on_delete=models.CASCADE, 
        related_name='history'
    )
    date = models.DateField("Дата")
    amount = models.DecimalField("Сумма", max_digits=12, decimal_places=2)
    note = models.CharField("Примечание", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "История цели"
        verbose_name_plural = "Истории целей"
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.goal.name} - {self.date}: {self.amount} ₽"


class Account(models.Model):
    """Финансовый счёт (банковский счёт, брокерский счёт, наличные)"""
    ACCOUNT_TYPES = [
        ('bank', '🏦 Банковский счёт'),
        ('card', '💳 Карта'),
        ('broker', '📈 Брокерский счёт'),
        ('cash', '💵 Наличные'),
        ('deposit', '🏛️ Вклад'),
        ('other', '📋 Другое'),
    ]
    
    name = models.CharField("Название", max_length=100)
    account_type = models.CharField("Тип счёта", max_length=20, choices=ACCOUNT_TYPES)
    balance = models.DecimalField("Текущий баланс", max_digits=15, decimal_places=2, default=0)
    currency = models.CharField("Валюта", max_length=3, default='RUB')
    description = models.TextField("Описание", blank=True)
    is_active = models.BooleanField("Активен", default=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Счёт"
        verbose_name_plural = "Счета"
        ordering = ['-account_type', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.balance:,.2f} {self.currency})"


class Transaction(models.Model):
    """Финансовая транзакция"""
    TRANSACTION_TYPES = [
        ('income', 'Доход'),
        ('expense', 'Расход'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    goal = models.ForeignKey(
        FinancialGoal, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Финансовая цель"
    )
    account = models.ForeignKey(
        Account, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Счёт"
    )
    external_id = models.CharField(
        "Внешний ID", 
        max_length=100, 
        blank=True, 
        null=True,
        unique=True,
        help_text="Уникальный идентификатор из банка (код авторизации)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Транзакция'
        verbose_name_plural = 'Транзакции'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'transaction_type']),
        ]
    
    def __str__(self):
        sign = '+' if self.transaction_type == 'income' else '-'
        return f"{sign}{self.amount} ₽ — {self.description or 'Без описания'}"
    
    @property
    def is_income(self):
        return self.transaction_type == 'income'
    
    @property
    def is_expense(self):
        return self.transaction_type == 'expense'


class Budget(models.Model):
    """Месячный бюджет по категории"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    month = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Бюджет'
        verbose_name_plural = 'Бюджеты'
        unique_together = ['user', 'category', 'month']
        ordering = ['-month']
    
    def __str__(self):
        return f"{self.category} ({self.month.strftime('%Y-%m')}): {self.amount} ₽"