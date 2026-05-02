from django.db import models


class Transaction(models.Model):
    INCOME = 'income'
    EXPENSE = 'expense'
    TYPE_CHOICES = [
        (INCOME, 'Income'),
        (EXPENSE, 'Expense'),
    ]

    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    category = models.CharField(max_length=100, blank=True)
    date = models.DateField()
    note = models.TextField(blank=True)
    order_number = models.CharField(max_length=100, blank=True, default='')
    store = models.ForeignKey(
        'stores.Store', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='transactions'
    )
    vendor = models.ForeignKey(
        'vendors.Vendor', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.title} — {'+'if self.type == self.INCOME else '-'}${self.amount}"
