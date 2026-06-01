from django import forms
from django.core.validators import FileExtensionValidator
from .models import Transaction, Category, Budget


class CSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label='Файл выписки (CSV или PDF)',
        validators=[FileExtensionValidator(allowed_extensions=['csv', 'pdf'])],
        help_text='Поддерживаются: CSV (Тинькофф/Сбер) и PDF (СберБанк Онлайн)',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.csv,.pdf'})
    )
    def clean_csv_file(self):
        file = self.cleaned_data['csv_file']
        if file.size > 10 * 1024 * 1024:
            raise forms.ValidationError('Файл слишком большой (макс. 10 МБ)')
        return file


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['category', 'amount', 'transaction_type', 'description', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.TextInput(attrs={'placeholder': 'Описание', 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['category'].queryset = Category.objects.filter(user=user, is_active=True)