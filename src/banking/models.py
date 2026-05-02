from django.db import models


ACCOUNT_TYPE_CHOICES = [
    ('checking',  'Checking'),
    ('savings',   'Savings'),
    ('credit',    'Credit Card'),
    ('business',  'Business Checking'),
    ('other',     'Other'),
]


class BankAccount(models.Model):
    name         = models.CharField(max_length=200)
    bank_name    = models.CharField(max_length=200, blank=True)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default='checking')
    last4        = models.CharField(max_length=4, blank=True)
    active       = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class BankTransaction(models.Model):
    TYPES = [
        ('credit', 'Credit'),
        ('debit',  'Debit'),
    ]

    account      = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='transactions')
    date         = models.DateField()
    description  = models.CharField(max_length=500)
    amount       = models.DecimalField(max_digits=12, decimal_places=2)
    type         = models.CharField(max_length=10, choices=TYPES)
    category     = models.CharField(max_length=100, blank=True)
    note         = models.TextField(blank=True)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.date} | {self.description} | {self.amount}"
