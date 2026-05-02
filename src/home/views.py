import json
from collections import defaultdict
from django.shortcuts import render, redirect
from django.db.models import Sum
from decimal import Decimal
from .models import Transaction
from .forms import TransactionForm


def add_transaction(request):
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('home')
    else:
        form = TransactionForm()
    return render(request, 'home/add_transaction.html', {'form': form})


def index(request):
    from stores.models import Store

    transactions = Transaction.objects.all()

    total_income = transactions.filter(type=Transaction.INCOME).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')

    total_expenses = transactions.filter(type=Transaction.EXPENSE).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')

    profit = total_income - total_expenses
    recent = transactions.select_related('store')[:10]

    # Per-store stats
    stores = Store.objects.select_related('group').all()
    grouped = {}
    ungrouped = []

    for store in stores:
        store_txns = transactions.filter(store=store)
        s_income = store_txns.filter(type=Transaction.INCOME).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        s_expenses = store_txns.filter(type=Transaction.EXPENSE).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        store.stat_income = s_income
        store.stat_expenses = s_expenses
        store.stat_profit = s_income - s_expenses
        store.stat_tx_count = store_txns.count()

        if store.group_id:
            gid = store.group_id
            if gid not in grouped:
                grouped[gid] = {
                    'group': store.group,
                    'stores': [],
                    'income': Decimal('0'),
                    'expenses': Decimal('0'),
                }
            grouped[gid]['stores'].append(store)
            grouped[gid]['income'] += s_income
            grouped[gid]['expenses'] += s_expenses
        else:
            ungrouped.append(store)

    for g in grouped.values():
        g['profit'] = g['income'] - g['expenses']

    # ── Chart data ──────────────────────────────────────────────────────
    # Daily income / expenses time series
    daily_raw = (Transaction.objects
        .values('date', 'type')
        .annotate(total=Sum('amount'))
        .order_by('date'))
    daily_map = defaultdict(lambda: {'income': 0.0, 'expense': 0.0})
    for row in daily_raw:
        daily_map[row['date']][row['type']] = float(row['total'])
    date_keys = sorted(daily_map.keys())
    chart_daily = {
        'labels':   [f"{d.month}/{d.day}" for d in date_keys],
        'income':   [daily_map[d]['income']  for d in date_keys],
        'expenses': [daily_map[d]['expense'] for d in date_keys],
        'profit':   [round(daily_map[d]['income'] - daily_map[d]['expense'], 2) for d in date_keys],
    }

    # Per-store comparison chart
    all_stores_flat = [s for g in grouped.values() for s in g['stores']] + ungrouped
    chart_stores = {
        'labels':   [s.name for s in all_stores_flat],
        'income':   [float(s.stat_income)   for s in all_stores_flat],
        'expenses': [float(s.stat_expenses) for s in all_stores_flat],
        'profit':   [float(s.stat_profit)   for s in all_stores_flat],
    }

    context = {
        'total_income': total_income,
        'total_expenses': total_expenses,
        'profit': profit,
        'recent_transactions': recent,
        'transaction_count': transactions.count(),
        'store_groups': list(grouped.values()),
        'ungrouped_stores': ungrouped,
        'has_stores': stores.exists(),
        'chart_daily': json.dumps(chart_daily),
        'chart_stores': json.dumps(chart_stores),
    }
    return render(request, 'home/index.html', context)
