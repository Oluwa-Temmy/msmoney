from django.shortcuts import render, redirect
from django.db.models import Sum
from decimal import Decimal, ROUND_HALF_UP
from .models import TaxProfile, FILING_STATUS_CHOICES, BUSINESS_TYPE_CHOICES
from home.models import Transaction
import datetime


# ── 2024 Federal income tax brackets ──────────────────────────────────────────
# Format: list of (rate, threshold_for_this_bracket)
# The last bracket has no upper limit (threshold = None)
BRACKETS = {
    'single': [
        (Decimal('0.10'),  Decimal('11600')),
        (Decimal('0.12'),  Decimal('47150')),
        (Decimal('0.22'),  Decimal('100525')),
        (Decimal('0.24'),  Decimal('191950')),
        (Decimal('0.32'),  Decimal('243725')),
        (Decimal('0.35'),  Decimal('609350')),
        (Decimal('0.37'),  None),
    ],
    'married_jointly': [
        (Decimal('0.10'),  Decimal('23200')),
        (Decimal('0.12'),  Decimal('94300')),
        (Decimal('0.22'),  Decimal('201050')),
        (Decimal('0.24'),  Decimal('383900')),
        (Decimal('0.32'),  Decimal('487450')),
        (Decimal('0.35'),  Decimal('731200')),
        (Decimal('0.37'),  None),
    ],
    'married_separately': [
        (Decimal('0.10'),  Decimal('11600')),
        (Decimal('0.12'),  Decimal('47150')),
        (Decimal('0.22'),  Decimal('100525')),
        (Decimal('0.24'),  Decimal('191950')),
        (Decimal('0.32'),  Decimal('243725')),
        (Decimal('0.35'),  Decimal('365600')),
        (Decimal('0.37'),  None),
    ],
    'head_of_household': [
        (Decimal('0.10'),  Decimal('16550')),
        (Decimal('0.12'),  Decimal('63100')),
        (Decimal('0.22'),  Decimal('100500')),
        (Decimal('0.24'),  Decimal('191950')),
        (Decimal('0.32'),  Decimal('243700')),
        (Decimal('0.35'),  Decimal('609350')),
        (Decimal('0.37'),  None),
    ],
}

STANDARD_DEDUCTIONS = {
    'single':             Decimal('14600'),
    'married_jointly':    Decimal('29200'),
    'married_separately': Decimal('14600'),
    'head_of_household':  Decimal('21900'),
}

# Self-employment tax: 15.3% on 92.35% of net SE income (employee + employer share)
SE_RATE          = Decimal('0.1530')
SE_INCOME_FACTOR = Decimal('0.9235')
# Deductible half of SE tax
SE_HALF_FACTOR   = Decimal('0.5')
# QBI deduction: 20% of qualified business income
QBI_RATE         = Decimal('0.20')
# Quarterly due dates (approximate)
QUARTERLY_DUE_DATES = ['April 15', 'June 17', 'September 16', 'January 15 (next yr)']


def _calc_tax(taxable_income: Decimal, filing_status: str) -> Decimal:
    """Calculate federal income tax from taxable income using 2024 brackets."""
    brackets = BRACKETS.get(filing_status, BRACKETS['single'])
    tax = Decimal('0')
    prev_threshold = Decimal('0')
    for rate, threshold in brackets:
        if threshold is None:
            # Top bracket — tax everything remaining
            if taxable_income > prev_threshold:
                tax += (taxable_income - prev_threshold) * rate
        else:
            bracket_income = min(taxable_income, threshold) - prev_threshold
            if bracket_income > 0:
                tax += bracket_income * rate
            prev_threshold = threshold
            if taxable_income <= threshold:
                break
    return tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _two(d: Decimal) -> str:
    return str(d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _pct(d: Decimal) -> str:
    return str((d * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def tax_dashboard(request):
    year = int(request.GET.get('year', datetime.date.today().year))

    # Load or build a blank profile for this year
    profile = TaxProfile.objects.filter(year=year).first()

    # Pull all transaction data for the selected year
    txns = Transaction.objects.filter(date__year=year)
    gross_income  = txns.filter(type='income').aggregate(t=Sum('amount'))['t']  or Decimal('0')
    total_expenses = txns.filter(type='expense').aggregate(t=Sum('amount'))['t'] or Decimal('0')
    net_business  = gross_income - total_expenses   # net profit from business

    # Per-store breakdown
    from stores.models import Store
    stores = Store.objects.all()
    store_rows = []
    for s in stores:
        s_inc = txns.filter(store=s, type='income').aggregate(t=Sum('amount'))['t']  or Decimal('0')
        s_exp = txns.filter(store=s, type='expense').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        store_rows.append({
            'name':    s.name,
            'income':  s_inc,
            'expenses': s_exp,
            'net':     s_inc - s_exp,
        })

    if profile:
        filing_status    = profile.filing_status
        other_income     = profile.other_income
        extra_deductions = profile.extra_deductions
        state_rate       = profile.state_tax_rate / 100
        qbi_eligible     = profile.qbi_eligible
        business_type    = profile.business_type
        owner_salary     = profile.owner_salary
    else:
        filing_status    = 'single'
        other_income     = Decimal('0')
        extra_deductions = Decimal('0')
        state_rate       = Decimal('0')
        qbi_eligible     = True
        business_type    = 'sole_prop'
        owner_salary     = Decimal('0')

    # ── Step 1: Self-employment tax ──────────────────────────────────────────
    # S-Corps: SE tax applies only to the owner's W-2 salary, not distributions
    if business_type == 's_corp':
        se_base = max(owner_salary, Decimal('0')) * SE_INCOME_FACTOR
    else:
        se_base = max(net_business, Decimal('0')) * SE_INCOME_FACTOR
    se_tax      = se_base * SE_RATE
    se_half_ded = (se_tax * SE_HALF_FACTOR)                    # deductible against income tax

    # ── Step 2: QBI deduction ────────────────────────────────────────────────
    qbi_deduction = (max(net_business, Decimal('0')) * QBI_RATE) if qbi_eligible else Decimal('0')

    # ── Step 3: Adjusted gross income ────────────────────────────────────────
    agi = net_business + other_income - se_half_ded

    # ── Step 4: Taxable income ───────────────────────────────────────────────
    std_ded    = STANDARD_DEDUCTIONS.get(filing_status, STANDARD_DEDUCTIONS['single'])
    total_ded  = std_ded + extra_deductions + qbi_deduction
    taxable    = max(agi - total_ded, Decimal('0'))

    # ── Step 5: Federal income tax ───────────────────────────────────────────
    federal_income_tax = _calc_tax(taxable, filing_status)

    # ── Step 6: State tax ────────────────────────────────────────────────────
    state_tax = (agi * state_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # ── Step 7: Totals ───────────────────────────────────────────────────────
    total_tax         = se_tax + federal_income_tax + state_tax
    effective_rate    = (total_tax / gross_income * 100) if gross_income else Decimal('0')
    quarterly_payment = (total_tax / 4).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Determine which quarter we're in for a "you should have paid" indicator
    today = datetime.date.today()
    quarters_elapsed = min((today.month - 1) // 3 + 1, 4) if today.year == year else (4 if today.year > year else 0)
    amount_should_have_paid = quarterly_payment * quarters_elapsed

    available_years = list(
        Transaction.objects.dates('date', 'year', order='DESC').values_list('date__year', flat=True)
    ) or [year]

    # Build bracket breakdown for display
    brackets_display = []
    prev = Decimal('0')
    for rate, threshold in BRACKETS.get(filing_status, BRACKETS['single']):
        upper = threshold if threshold else '∞'
        in_bracket = Decimal('0')
        if threshold is None:
            in_bracket = max(taxable - prev, Decimal('0'))
        else:
            in_bracket = max(min(taxable, threshold) - prev, Decimal('0'))
        if in_bracket > 0:
            brackets_display.append({
                'rate':       _pct(rate) + '%',
                'from':       _two(prev),
                'to':         _two(threshold) if threshold else '—',
                'income':     _two(in_bracket),
                'tax':        _two((in_bracket * rate).quantize(Decimal('0.01'), ROUND_HALF_UP)),
            })
        if threshold:
            prev = threshold
        if threshold and taxable <= threshold:
            break

    ctx = {
        'year':               year,
        'available_years':    available_years,
        'profile':            profile,
        'filing_status':      filing_status,
        'filing_status_choices': FILING_STATUS_CHOICES,
        'business_type':      business_type,
        'business_type_choices': BUSINESS_TYPE_CHOICES,
        'owner_salary':       owner_salary,
        'store_rows':         store_rows,
        # Income
        'gross_income':       gross_income,
        'total_expenses':     total_expenses,
        'net_business':       net_business,
        'other_income':       other_income,
        # Deductions
        'std_deduction':      std_ded,
        'extra_deductions':   extra_deductions,
        'qbi_deduction':      qbi_deduction,
        'qbi_eligible':       qbi_eligible,
        'total_deductions':   total_ded,
        'se_half_ded':        se_half_ded,
        # Calculated
        'agi':                agi,
        'taxable':            taxable,
        'se_tax':             se_tax,
        'federal_income_tax': federal_income_tax,
        'state_tax':          state_tax,
        'state_rate':         profile.state_tax_rate if profile else Decimal('0'),
        'total_tax':          total_tax,
        'effective_rate':     effective_rate.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP),
        'quarterly_payment':  quarterly_payment,
        'quarterly_due_dates': QUARTERLY_DUE_DATES,
        'quarters_elapsed':   quarters_elapsed,
        'amount_should_have_paid': amount_should_have_paid,
        'brackets_display':   brackets_display,
    }
    return render(request, 'taxes/dashboard.html', ctx)


def save_profile(request):
    if request.method != 'POST':
        return redirect('tax_dashboard')
    year             = int(request.POST.get('year', datetime.date.today().year))
    filing_status    = request.POST.get('filing_status', 'single')
    business_type    = request.POST.get('business_type', 'sole_prop')
    owner_salary     = Decimal(request.POST.get('owner_salary', '0') or '0')
    other_income     = Decimal(request.POST.get('other_income', '0') or '0')
    extra_deductions = Decimal(request.POST.get('extra_deductions', '0') or '0')
    state_tax_rate   = Decimal(request.POST.get('state_tax_rate', '0') or '0')
    qbi_eligible     = request.POST.get('qbi_eligible') == 'on'
    notes            = request.POST.get('notes', '')

    TaxProfile.objects.update_or_create(
        year=year,
        defaults=dict(
            filing_status=filing_status,
            business_type=business_type,
            owner_salary=owner_salary,
            other_income=other_income,
            extra_deductions=extra_deductions,
            state_tax_rate=state_tax_rate,
            qbi_eligible=qbi_eligible,
            notes=notes,
        )
    )
    return redirect(f'/taxes/?year={year}')
