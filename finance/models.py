from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator


class Category(models.Model):
    NAME_CHOICES = [
        ('food', '🍔 Еда'), ('transport', ' Транспорт'), ('entertainment', '🎬 Развлечения'),
        ('utilities', '💡 Коммуналка'), ('health', '🏥 Здоровье'), ('education', '📚 Образование'),
        ('salary', '💰 Зарплата'), ('freelance', '💻 Фриланс'), ('investments', '📈 Инвестиции'),
        ('other', ' Другое'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='categories')
    name = models.CharField(max_length=50, choices=NAME_CHOICES, db_index=True)
    color = models.CharField(max_length=7, default='#3498db')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['user', 'name'], name='unique_user_category')]

    def __str__(self):
        return self.get_name_display()

    def get_transactions_count(self):
        return self.transaction_set.count()


class Transaction(models.Model):
    TYPE_CHOICES = [('income', 'Доход'), ('expense', 'Расход')]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    date = models.DateField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'transaction_type', 'date']),
        ]

    def __str__(self):
        sign = '+' if self.transaction_type == 'income' else '−'
        return f"{sign}{self.amount:.2f} ₽ — {self.description or self.category}"

    def is_expense(self): return self.transaction_type == 'expense'
    def is_income(self): return self.transaction_type == 'income'


class Budget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='budgets')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='budgets')
    limit = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    month = models.DateField(help_text='Первый день месяца')
    notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-month']
        constraints = [models.UniqueConstraint(fields=['user', 'category', 'month'], name='unique_monthly_budget')]

    def __str__(self):
        return f"{self.category}: {self.limit:.2f} ₽ ({self.month:%Y-%m})"

    def get_spent(self):
        from django.db.models import Sum
        spent = self.category.transactions.filter(
            user=self.user, transaction_type='expense',
            date__year=self.month.year, date__month=self.month.month
        ).aggregate(total=Sum('amount'))['total']
        return float(spent or 0)

    def get_remaining(self): return max(0, float(self.limit) - self.get_spent())
    def is_over_budget(self): return self.get_spent() > float(self.limit)