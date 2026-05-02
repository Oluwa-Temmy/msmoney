from django.db import models


class StoreGroup(models.Model):
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Store(models.Model):
    PLATFORM_CHOICES = [
        ('amazon', 'Amazon Seller'),
        ('ebay', 'eBay Store'),
        ('shopify', 'Shopify'),
        ('etsy', 'Etsy'),
        ('walmart', 'Walmart Marketplace'),
        ('local', 'Local / Brick & Mortar'),
        ('service', 'Service Business'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='other')
    description = models.TextField(blank=True)
    url = models.URLField(blank=True, help_text='Storefront or seller profile URL')
    active = models.BooleanField(default=True)
    group = models.ForeignKey(
        StoreGroup, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='stores'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Store'
        verbose_name_plural = 'Stores'

    def __str__(self):
        return f"{self.name} ({self.get_platform_display()})"
