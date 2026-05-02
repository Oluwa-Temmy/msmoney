from django.contrib import admin
from .models import Store


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('name', 'platform', 'active', 'created_at')
    list_filter = ('platform', 'active')
    search_fields = ('name', 'description')
