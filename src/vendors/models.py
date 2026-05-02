from django.db import models


VENDOR_CATEGORY_CHOICES = [
    ('supplier',    'Supplier / Manufacturer'),
    ('shipping',    'Shipping / Fulfillment'),
    ('platform',    'Marketplace / Platform Fee'),
    ('payment',     'Payment Processor'),
    ('advertising', 'Advertising / Marketing'),
    ('software',    'Software / SaaS'),
    ('returns',     'Returns / Refunds'),
    ('warehouse',   'Warehouse / Storage'),
    ('other',       'Other'),
]

FEE_TYPE_CHOICES = [
    ('flat',       'Flat Fee'),
    ('percentage', 'Percentage of Sales'),
    ('per_unit',   'Per Unit / Per Order'),
    ('variable',   'Variable'),
]


class Vendor(models.Model):
    store     = models.ForeignKey(
        'stores.Store', on_delete=models.CASCADE, related_name='vendors'
    )
    name      = models.CharField(max_length=200)
    category  = models.CharField(max_length=20, choices=VENDOR_CATEGORY_CHOICES, default='other')
    fee_type  = models.CharField(max_length=20, choices=FEE_TYPE_CHOICES, default='variable')
    fee_value = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
        help_text='Flat dollar amount or percentage (e.g. 15 for 15%)'
    )
    website    = models.URLField(blank=True)
    notes      = models.TextField(blank=True)
    active     = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"
