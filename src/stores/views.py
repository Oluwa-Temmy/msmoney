from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db.models import Sum
from decimal import Decimal
import json
from collections import defaultdict
from .models import Store, StoreGroup
from .forms import StoreForm


def _store_stats(store_qs):
    """Return (income, expenses, profit, tx_count) for a queryset of stores."""
    from home.models import Transaction
    txns = Transaction.objects.filter(store__in=store_qs)
    income   = txns.filter(type='income').aggregate(t=Sum('amount'))['t']  or Decimal('0')
    expenses = txns.filter(type='expense').aggregate(t=Sum('amount'))['t'] or Decimal('0')
    return income, expenses, income - expenses, txns.count()


def store_list(request):
    groups = StoreGroup.objects.prefetch_related('stores').all()
    group_data = []
    for g in groups:
        stores = list(g.stores.all())
        income, expenses, profit, tx_count = _store_stats(g.stores.all())
        for s in stores:
            si, se, sp, stx = _store_stats(Store.objects.filter(pk=s.pk))
            s.stat_income   = si
            s.stat_expenses = se
            s.stat_profit   = sp
            s.stat_tx_count = stx
        group_data.append({
            'group':    g,
            'stores':   stores,
            'income':   income,
            'expenses': expenses,
            'profit':   profit,
            'tx_count': tx_count,
        })

    ungrouped = Store.objects.filter(group__isnull=True)
    ungrouped_list = []
    for s in ungrouped:
        si, se, sp, stx = _store_stats(Store.objects.filter(pk=s.pk))
        s.stat_income   = si
        s.stat_expenses = se
        s.stat_profit   = sp
        s.stat_tx_count = stx
        ungrouped_list.append(s)

    return render(request, 'stores/list.html', {
        'group_data':       group_data,
        'ungrouped_stores': ungrouped_list,
        'chart_stores': json.dumps({
            'labels':   [s.name for s in (
                [st for gd in group_data for st in gd['stores']] + ungrouped_list
            )],
            'income':   [float(s.stat_income)   for s in (
                [st for gd in group_data for st in gd['stores']] + ungrouped_list
            )],
            'expenses': [float(s.stat_expenses) for s in (
                [st for gd in group_data for st in gd['stores']] + ungrouped_list
            )],
            'profit':   [float(s.stat_profit)   for s in (
                [st for gd in group_data for st in gd['stores']] + ungrouped_list
            )],
        }),
        'chart_groups': json.dumps({
            'labels':   [gd['group'].name for gd in group_data],
            'income':   [float(gd['income'])   for gd in group_data],
            'expenses': [float(gd['expenses']) for gd in group_data],
            'profit':   [float(gd['profit'])   for gd in group_data],
        }),
    })


def add_store(request):
    name_error = request.session.pop('store_name_error', None)
    initial_data = request.session.pop('store_form_data', None)

    if request.method == 'POST':
        form = StoreForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            existing = Store.objects.filter(name__iexact=name).first()
            if existing:
                request.session['pending_store'] = {
                    'name': form.cleaned_data['name'],
                    'platform': form.cleaned_data['platform'],
                    'description': form.cleaned_data['description'],
                    'url': form.cleaned_data['url'],
                    'active': form.cleaned_data['active'],
                }
                return redirect(
                    reverse('confirm_group') + f'?existing_id={existing.id}'
                )
            form.save()
            return redirect('store_list')
    else:
        form = StoreForm(initial=initial_data)

    return render(request, 'stores/add.html', {'form': form, 'name_error': name_error})


def confirm_group(request):
    existing_id = request.GET.get('existing_id') or request.POST.get('existing_id')
    existing = get_object_or_404(Store, id=existing_id)
    pending = request.session.get('pending_store')

    if not pending:
        return redirect('add_store')

    if request.method == 'POST':
        choice = request.POST.get('choice')
        if choice == 'group':
            new_store = Store(
                name=pending['name'],
                platform=pending['platform'],
                description=pending['description'],
                url=pending['url'],
                active=pending['active'],
            )
            if existing.group:
                group = existing.group
            else:
                group = StoreGroup.objects.create(name=pending['name'])
                existing.group = group
                existing.save()
            new_store.group = group
            new_store.save()
            request.session.pop('pending_store', None)
            return redirect('store_list')
        else:
            # Not related — send back with error, re-populate form
            request.session['store_name_error'] = (
                f'A store named "{pending["name"]}" already exists. '
                'Please choose a different name.'
            )
            request.session['store_form_data'] = pending
            request.session.pop('pending_store', None)
            return redirect('add_store')

    platform_display = dict(Store.PLATFORM_CHOICES).get(
        pending['platform'], pending['platform']
    )
    return render(request, 'stores/confirm_group.html', {
        'existing': existing,
        'pending_name': pending['name'],
        'pending_platform': platform_display,
        'existing_id': existing_id,
    })


def delete_store(request, store_id):
    store = get_object_or_404(Store, id=store_id)
    if request.method == 'POST':
        # If this was the only store in a group, clean up the group too
        if store.group:
            group = store.group
            store.delete()
            if not group.stores.exists():
                group.delete()
        else:
            store.delete()
        return redirect('store_list')
    return render(request, 'stores/delete_confirm.html', {'store': store})


def group_store(request, store_id):
    """Manually group a store with another existing store."""
    store = get_object_or_404(Store, id=store_id)
    other_stores = Store.objects.exclude(id=store_id)

    if request.method == 'POST':
        target_id = request.POST.get('target_id')
        target = get_object_or_404(Store, id=target_id)

        if target.group:
            group = target.group
        else:
            group = StoreGroup.objects.create(name=target.name)
            target.group = group
            target.save()

        store.group = group
        store.save()
        return redirect('store_list')

    return render(request, 'stores/group_store.html', {
        'store': store,
        'other_stores': other_stores,
    })


def rename_group(request, group_id):
    group = get_object_or_404(StoreGroup, id=group_id)
    error = None
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            group.name = name
            group.save()
            return redirect('store_list')
        error = 'Name cannot be empty.'
    return render(request, 'stores/rename_group.html', {'group': group, 'error': error})


def ungroup_store(request, store_id):
    """Remove a store from its group."""
    store = get_object_or_404(Store, id=store_id)
    if request.method == 'POST':
        group = store.group
        store.group = None
        store.save()
        if group and not group.stores.exists():
            group.delete()
        return redirect('store_list')
    return render(request, 'stores/ungroup_confirm.html', {'store': store})


def import_amazon_csv(request, store_id):
    import csv, io
    from decimal import Decimal, InvalidOperation
    from datetime import datetime
    from home.models import Transaction

    store = get_object_or_404(Store, id=store_id)
    session_key = f'amazon_import_{store_id}'

    # ── Stage 2: Confirm & save (rows come from session) ──
    if request.method == 'POST' and 'confirm' in request.POST:
        rows = request.session.get(session_key, [])
        if not rows:
            return render(request, 'stores/import_csv.html', {
                'store': store, 'preview': False,
                'import_error': 'Session expired or no rows found — please re-upload the CSV.',
            })
        selected_raw = {i for i in request.POST.getlist('selected_indices') if i}
        # If no valid indices submitted (all-checked default scenario where browser omits unchecked),
        # fall back to importing all rows.
        if selected_raw:
            selected_indices = selected_raw
        else:
            selected_indices = {str(i) for i in range(len(rows))}
        saved = 0
        errors = []
        for i, row in enumerate(rows):
            if str(i) not in selected_indices:
                continue
            try:
                Transaction.objects.create(
                    date=datetime.strptime(row['date'], '%Y-%m-%d').date(),
                    title=row['title'],
                    amount=Decimal(str(row['amount'])),
                    type=row['type'],
                    category=row.get('category', ''),
                    note=row.get('note', ''),
                    order_number=row.get('order_number', ''),
                    store=store,
                )
                saved += 1
            except Exception as e:
                errors.append(f'Row {i}: {e}')
        if errors:
            import logging
            logging.getLogger(__name__).error('Amazon import errors: %s', errors)
        request.session.pop(session_key, None)
        if not saved and errors:
            return render(request, 'stores/import_csv.html', {
                'store': store, 'preview': False,
                'import_error': f'{len(errors)} row(s) failed. First error: {errors[0]}',
            })
        return redirect(reverse('store_detail', args=[store_id]) + f'?imported={saved}')

    # ── Stage 1: Parse CSV ──
    elif request.method == 'POST' and 'csv_file' in request.FILES:
        raw = request.FILES['csv_file'].read()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')

        reader = csv.DictReader(io.StringIO(text))
        rows = []
        skipped = 0

        DATE_FMTS = [
            '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y',
            '%b %d, %Y %I:%M:%S %p', '%b %d, %Y %I:%M:%S %p %Z',
            '%b %d, %Y', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S',
        ]

        def _parse_date(raw_val):
            """Try multiple date formats; return YYYY-MM-DD string or None."""
            s = raw_val.strip()
            # strip trailing timezone label like " UTC"
            for tz in (' UTC', ' PST', ' PDT', ' EST', ' EDT'):
                s = s.replace(tz, '')
            s = s.strip()
            for fmt in DATE_FMTS:
                try:
                    return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
                except ValueError:
                    continue
            return None

        def _pick_amount(*candidates):
            """Return the first candidate that parses as a non-zero Decimal, or None."""
            for val in candidates:
                if not val:
                    continue
                cleaned = val.strip().replace(',', '').replace('$', '')
                if not cleaned or cleaned in ('---', '-', '+', 'n/a', 'N/A', 'N/a'):
                    continue
                try:
                    return Decimal(cleaned)
                except (InvalidOperation, ValueError):
                    continue
            return None

        for row in reader:
            # Normalise all headers to lowercase stripped
            norm = {k.strip().lower(): v.strip() for k, v in row.items()}

            # Total — try multiple column names; skip non-numeric values (e.g. '---')
            total = _pick_amount(
                norm.get('total (usd)', ''),
                norm.get('total', ''),
                norm.get('total (cad)', ''),
                norm.get('amount', ''),
            )
            if total is None or total == 0:
                skipped += 1
                continue

            tx_type = 'income' if total > 0 else 'expense'

            # Column aliases
            tx_type_label = (norm.get('transaction type') or norm.get('type') or '').strip()
            product       = (norm.get('product details') or norm.get('description') or
                             norm.get('product') or norm.get('sku') or '').strip()
            order_id      = (norm.get('order id') or norm.get('order_id') or
                             norm.get('order number') or '').strip()
            status        = (norm.get('transaction status') or norm.get('status') or '').strip()
            date_raw      = (norm.get('date/time') or norm.get('date') or
                             norm.get('date created') or '').strip()

            parsed_date = _parse_date(date_raw)
            if not parsed_date:
                skipped += 1
                continue

            clean_order = order_id if order_id and order_id != '---' else ''
            note_parts = []
            if clean_order:
                note_parts.append(f"Order: {clean_order}")
            if status:
                note_parts.append(f"Status: {status}")
            note_str = ' | '.join(note_parts)

            # For Order Payment rows: use gross (Total product charges) as income
            # and auto-create a linked Amazon Fees expense from the same row.
            if tx_type_label.lower() == 'order payment':
                gross = _pick_amount(norm.get('total product charges', ''))
                fees  = _pick_amount(norm.get('amazon fees', ''))
                use_amount = gross if (gross and gross > 0) else abs(total)
                rows.append({
                    'date':         parsed_date,
                    'title':        (product or 'Order Payment')[:200],
                    'amount':       str(use_amount),
                    'type':         'income',
                    'category':     tx_type_label,
                    'note':         note_str,
                    'order_number': clean_order,
                })
                if fees and fees != 0:
                    rows.append({
                        'date':         parsed_date,
                        'title':        f'Amazon Fees: {product or clean_order}'[:200],
                        'amount':       str(abs(fees)),
                        'type':         'expense',
                        'category':     'Amazon Fees',
                        'note':         note_str,
                        'order_number': clean_order,
                    })
            else:
                title = (f"{tx_type_label}: {product}" if product else tx_type_label or 'Transaction')[:200]
                rows.append({
                    'date':         parsed_date,
                    'title':        title,
                    'amount':       str(abs(total)),
                    'type':         tx_type,
                    'category':     tx_type_label,
                    'note':         note_str,
                    'order_number': clean_order,
                })

        # collect headers for debug display in empty state
        detected_headers = list({k.strip().lower() for k in (reader.fieldnames or [])})

        # Store parsed rows in session so confirm step doesn't rely on hidden fields
        request.session[session_key] = rows
        request.session.modified = True
        request.session.save()

        return render(request, 'stores/import_csv.html', {
            'store': store,
            'rows': rows,
            'skipped': skipped,
            'preview': True,
            'detected_headers': detected_headers,
        })

    # Clear any stale session on fresh GET
    request.session.pop(session_key, None)
    return render(request, 'stores/import_csv.html', {'store': store, 'preview': False})


def bulk_transactions(request, store_id):
    from home.models import Transaction
    store = get_object_or_404(Store, id=store_id)
    if request.method == 'POST':
        action = request.POST.get('action')
        ids = request.POST.getlist('tx_ids')
        if ids:
            qs = Transaction.objects.filter(store=store, id__in=ids)
            if action == 'delete':
                count = qs.count()
                qs.delete()
                return redirect(reverse('store_detail', args=[store_id]) + f'?deleted={count}')
    return redirect('store_detail', store_id=store_id)


def store_detail(request, store_id):
    from home.models import Transaction
    from vendors.models import Vendor
    store = get_object_or_404(Store, id=store_id)
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    tx_qs = Transaction.objects.filter(store=store).select_related('vendor').order_by('-date', '-created_at')
    paginator = Paginator(tx_qs, 13)  # Change 13 to 10 for 10 per page
    page = request.GET.get('page')
    try:
        transactions = paginator.page(page)
    except PageNotAnInteger:
        transactions = paginator.page(1)
    except EmptyPage:
        transactions = paginator.page(paginator.num_pages)

    # Build per-order profit: for each income tx, find linked expense txs by order_number
    _expense_by_order = defaultdict(list)
    for tx in transactions:
        if tx.type == 'expense' and tx.order_number:
            _expense_by_order[tx.order_number].append(tx)

    linked_expense_ids = set()
    for tx in transactions:
        if tx.type == 'income' and tx.order_number and tx.order_number in _expense_by_order:
            tx.linked_expenses = _expense_by_order[tx.order_number]
            amazon_fees  = sum(e.amount for e in tx.linked_expenses if e.category != 'Printify Order')
            production   = sum(e.amount for e in tx.linked_expenses if e.category == 'Printify Order')
            tx.col_revenue    = tx.amount
            tx.col_amazon_fees = amazon_fees if amazon_fees else None
            tx.col_production  = production  if production  else None
            tx.order_profit    = tx.amount - amazon_fees - production
            for e in tx.linked_expenses:
                linked_expense_ids.add(e.id)
        else:
            tx.linked_expenses  = []
            tx.col_revenue      = None
            tx.col_amazon_fees  = None
            tx.col_production   = None
            tx.order_profit     = None

    # Flag expenses that are shown as sub-rows so the template can skip them at top level
    for tx in transactions:
        tx.is_linked_expense = tx.id in linked_expense_ids
    income, expenses, profit, tx_count = _store_stats(Store.objects.filter(pk=store_id))

    # Amazon-specific profit: gross order revenue minus Amazon fees only (excludes production)
    from home.models import Transaction as _Tx
    amazon_gross = _Tx.objects.filter(store=store, type='income', category='Order Payment').aggregate(t=Sum('amount'))['t'] or Decimal('0')
    amazon_fees_total = _Tx.objects.filter(store=store, type='expense', category='Amazon Fees').aggregate(t=Sum('amount'))['t'] or Decimal('0')
    sales_profit = amazon_gross - amazon_fees_total

    vendors = Vendor.objects.filter(store=store)

    # Daily chart data for this store
    from django.db.models import Count
    daily_raw = (Transaction.objects
        .filter(store=store)
        .values('date', 'type')
        .annotate(total=Sum('amount'), cnt=Count('id'))
        .order_by('date'))
    daily_map = defaultdict(lambda: {'income': 0.0, 'expense': 0.0, 'income_count': 0})
    for row in daily_raw:
        daily_map[row['date']][row['type']] = float(row['total'])
        if row['type'] == 'income':
            daily_map[row['date']]['income_count'] += row['cnt']
    date_keys = sorted(daily_map.keys())
    chart_daily = {
        'labels':        [f"{d.month}/{d.day}" for d in date_keys],
        'income':        [daily_map[d]['income']        for d in date_keys],
        'expenses':      [daily_map[d]['expense']       for d in date_keys],
        'profit':        [round(daily_map[d]['income'] - daily_map[d]['expense'], 2) for d in date_keys],
        'income_counts': [daily_map[d]['income_count'] for d in date_keys],
    }

    return render(request, 'stores/store_detail.html', {
        'store': store,
        'transactions': transactions,
        'income': income,
        'expenses': expenses,
        'profit': profit,
        'tx_count': tx_count,
        'chart_daily': json.dumps(chart_daily),
        'vendors': vendors,
        'amazon_gross': amazon_gross,
        'amazon_fees_total': amazon_fees_total,
        'sales_profit': sales_profit,
        'paginator': paginator,
        'page_obj': transactions,
    })


