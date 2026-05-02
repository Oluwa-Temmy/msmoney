from django.db import models


FILING_STATUS_CHOICES = [
    ('single',             'Single'),
    ('married_jointly',    'Married Filing Jointly'),
    ('married_separately', 'Married Filing Separately'),
    ('head_of_household',  'Head of Household'),
]

BUSINESS_TYPE_CHOICES = [
    ('sole_prop',  'Sole Proprietor'),
    ('llc_single', 'Single-Member LLC'),
    ('llc_multi',  'Multi-Member LLC'),
    ('s_corp',     'S-Corporation'),
]


class TaxProfile(models.Model):
    """Per-year tax settings for the business owner."""
    year            = models.IntegerField(unique=True)
    business_type   = models.CharField(max_length=20, choices=BUSINESS_TYPE_CHOICES, default='sole_prop')
    owner_salary    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    filing_status   = models.CharField(max_length=20, choices=FILING_STATUS_CHOICES, default='single')
    # Other income outside the business (W-2, etc.)
    other_income    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Additional deductions beyond the standard deduction (e.g. home office, health insurance)
    extra_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # State income tax rate as a percentage (e.g. 5.0 for 5%)
    state_tax_rate  = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # QBI deduction eligible (20% pass-through deduction for sole props / S-corps)
    qbi_eligible    = models.BooleanField(default=True)
    notes           = models.TextField(blank=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-year']

    def __str__(self):
        return f'Tax Profile {self.year}'
