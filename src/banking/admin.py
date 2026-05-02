from django.contrib import admin
from .models import BankAccount, BankTransaction

admin.site.register(BankAccount)
admin.site.register(BankTransaction)
