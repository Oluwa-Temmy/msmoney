from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from decimal import Decimal, InvalidOperation
from stores.models import Store
from .models import Vendor, VENDOR_CATEGORY_CHOICES, FEE_TYPE_CHOICES


def vendors_all(request):
    """Global vendor list — all vendors across all stores."""
    vendors = Vendor.objects.select_related('store').order_by('store__name', 'name')
    for v in vendors:
        txns = v.transactions.all()
        v.stat_total    = txns.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        v.stat_tx_count = txns.count()
    return render(request, 'vendors/list.html', {
        'vendors':           vendors,
        'vendor_categories': VENDOR_CATEGORY_CHOICES,
    })


def vendor_list(request, store_id):
    store   = get_object_or_404(Store, id=store_id)
    vendors = store.vendors.all()
    for v in vendors:
        txns = v.transactions.all()
        v.stat_total    = txns.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        v.stat_tx_count = txns.count()
    return render(request, 'vendors/store_vendors.html', {
        'store':             store,
        'vendors':           vendors,
        'vendor_categories': VENDOR_CATEGORY_CHOICES,
        'fee_types':         FEE_TYPE_CHOICES,
    })


def add_vendor(request, store_id):
    store = get_object_or_404(Store, id=store_id)
    if request.method == 'POST':
        name      = request.POST.get('name', '').strip()
        category  = request.POST.get('category', 'other')
        fee_type  = request.POST.get('fee_type', 'variable')
        fee_value = request.POST.get('fee_value', '').strip() or None
        website   = request.POST.get('website', '').strip()
        notes     = request.POST.get('notes', '').strip()
        if name:
            Vendor.objects.create(
                store=store, name=name, category=category,
                fee_type=fee_type, fee_value=fee_value,
                website=website, notes=notes,
            )
    return redirect('vendor_list', store_id=store.id)


def delete_vendor(request, store_id, vendor_id):
    vendor = get_object_or_404(Vendor, id=vendor_id, store_id=store_id)
    if request.method == 'POST':
        vendor.delete()
    return redirect('vendor_list', store_id=store_id)


def vendor_manage(request, store_id, vendor_id):
    """Show all transactions linked to a vendor; allow bulk delete."""
    from home.models import Transaction
    from django.urls import reverse

    store  = get_object_or_404(Store, id=store_id)
    vendor = get_object_or_404(Vendor, id=vendor_id, store=store)

    if request.method == 'POST':
        ids = request.POST.getlist('tx_ids')
        if ids:
            Transaction.objects.filter(vendor=vendor, id__in=ids).delete()
        return redirect(reverse('vendor_manage', args=[store_id, vendor_id]))

    transactions = Transaction.objects.filter(vendor=vendor).order_by('-date', '-created_at')
    total = transactions.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    return render(request, 'vendors/vendor_manage.html', {
        'store':        store,
        'vendor':       vendor,
        'transactions': transactions,
        'total':        total,
    })


def import_vendor_invoices(request, store_id):
    """Import vendor invoices from a CSV file and create expense transactions."""
    import csv, io
    from datetime import datetime
    from home.models import Transaction

    store = get_object_or_404(Store, id=store_id)
    vendors = Vendor.objects.filter(store=store)
    vendor_map = {v.name.lower(): v for v in vendors}
    session_key = f'vendor_import_{store_id}'

    # ── Stage 3: Confirm & save ──
    if request.method == 'POST' and 'confirm' in request.POST:
        count = int(request.POST.get('row_count', 0))
        saved = 0
        for i in range(count):
            if request.POST.get(f'row_{i}_sel') != 'on':
                continue
            try:
                date = datetime.strptime(request.POST[f'row_{i}_date'], '%Y-%m-%d').date()
                vendor_id = request.POST.get(f'row_{i}_vendor_id') or None
                vendor = Vendor.objects.get(id=vendor_id, store=store) if vendor_id else None
                Transaction.objects.create(
                    date=date,
                    title=request.POST[f'row_{i}_title'],
                    amount=Decimal(request.POST[f'row_{i}_amount']),
                    type='expense',
                    category=request.POST.get(f'row_{i}_category', 'Vendor Invoice'),
                    note=request.POST.get(f'row_{i}_note', ''),
                    order_number=request.POST.get(f'row_{i}_order_number', ''),
                    store=store,
                    vendor=vendor,
                )
                saved += 1
            except Exception:
                continue
        from django.urls import reverse
        request.session.pop(session_key, None)
        return redirect(reverse('store_detail', args=[store_id]) + f'?imported={saved}')

    # ── Stage 2: Discovery confirmed → full preview from session ──
    if request.method == 'POST' and 'discover_confirmed' in request.POST:
        rows        = request.session.get(session_key, [])
        meta        = request.session.get(session_key + '_meta', {})
        is_printify = meta.get('is_printify', False)
        skipped     = meta.get('skipped', 0)
        matched_rows   = [r for r in rows if r.get('amazon_matched')]
        unmatched_rows = [r for r in rows if not r.get('amazon_matched')]
        total_revenue  = sum(Decimal(r['amazon_revenue']) for r in matched_rows) if matched_rows else Decimal('0')
        total_fees     = sum(Decimal(r.get('amazon_fees') or '0') for r in matched_rows) if matched_rows else Decimal('0')
        total_prod     = sum(Decimal(r['amount']) for r in matched_rows) if matched_rows else Decimal('0')
        total_net      = total_revenue - total_fees - total_prod
        return render(request, 'vendors/import_invoices.html', {
            'store': store, 'vendors': vendors,
            'rows': rows, 'skipped': skipped,
            'preview': True, 'discovery': False,
            'is_printify': is_printify,
            'matched_rows':    matched_rows,
            'unmatched_rows':  unmatched_rows,
            'total_revenue':   str(total_revenue),
            'total_fees':      str(total_fees),
            'total_prod':      str(total_prod),
            'total_net':       str(total_net),
        })

    # ── Stage 1: Parse CSV ──
    if request.method == 'POST' and 'csv_file' in request.FILES:
        raw = request.FILES['csv_file'].read()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')

        reader = csv.DictReader(io.StringIO(text))
        all_rows = list(reader)
        rows = []
        skipped = 0

        # ── Detect Printify format ──
        def _is_printify(raw_rows):
            if not raw_rows:
                return False
            headers = {k.strip().lower() for k in raw_rows[0].keys()}
            return 'printify id' in headers and 'total cost' in headers

        def _parse_usd(val):
            """Parse values like '18.01 USD' or '22.76' → Decimal."""
            return Decimal(val.replace('USD', '').replace(',', '').replace('$', '').strip())

        is_printify = _is_printify(all_rows)

        for row in all_rows:
            norm = {k.strip().lower(): v.strip() for k, v in row.items()}

            if is_printify:
                # ── Printify-specific parsing ──
                date_str     = norm.get('date created', '')[:10]  # "2026-04-01 04:11:50" → "2026-04-01"
                order_id     = norm.get('sales channel number') or norm.get('printify id', '')
                customer     = norm.get('customer name', '')
                status       = norm.get('order status', '')
                amount_str   = norm.get('total cost', '0')
                product_cost = norm.get('product cost', '0')
                ship_cost    = norm.get('shipping cost', '0')
                carrier      = norm.get('shipping carrier', '')
                title        = f"Order {order_id}" if order_id else 'Printify Order'
                note_parts   = [f"Customer: {customer}"] if customer else []
                if carrier:
                    note_parts.append(f"Carrier: {carrier}")
                if status and status != 'fulfilled':
                    note_parts.append(f"Status: {status}")
                note         = ' | '.join(note_parts)
                vendor_name  = 'printify'
                category     = 'Printify Order'
                extra        = {
                    'order_number': order_id,
                    'order_id':     order_id,
                    'customer':     customer,
                    'status':       status,
                    'product_cost': product_cost,
                    'ship_cost':    ship_cost,
                    'carrier':      carrier,
                }
            else:
                # ── Generic flexible parsing ──
                date_str    = norm.get('date') or norm.get('invoice date') or ''
                title       = norm.get('description') or norm.get('title') or norm.get('item') or ''
                amount_str  = norm.get('amount') or norm.get('total') or norm.get('cost') or ''
                vendor_name = norm.get('vendor') or norm.get('supplier') or norm.get('vendor name') or ''
                note        = norm.get('note') or norm.get('notes') or norm.get('reference') or ''
                category    = 'Vendor Invoice'
                extra       = {'order_number': ''}

            try:
                amount = abs(_parse_usd(amount_str))
            except (InvalidOperation, ValueError):
                skipped += 1
                continue

            # Parse date — try YYYY-MM-DD first (Printify already sliced to 10 chars), then others
            parsed_date = None
            for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m-%d-%Y'):
                try:
                    parsed_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
            if not parsed_date:
                skipped += 1
                continue

            matched_vendor = vendor_map.get(vendor_name.lower())
            row_data = {
                'date':           parsed_date.strftime('%Y-%m-%d'),
                'title':          title or vendor_name or 'Vendor Invoice',
                'amount':         str(amount),
                'vendor_id':      matched_vendor.id if matched_vendor else '',
                'vendor_display': matched_vendor.name if matched_vendor else vendor_name or '—',
                'note':           note,
                'category':       category,
                'is_printify':    is_printify,
            }
            row_data.update(extra)
            rows.append(row_data)

        # ── For Printify: look up matching Amazon transactions by order_number ──
        if is_printify:
            order_nums = [r['order_number'] for r in rows if r.get('order_number')]
            amazon_txs = Transaction.objects.filter(
                store=store,
                order_number__in=order_nums,
                type='income',
            ).values('order_number', 'amount', 'title')
            amazon_map = {}
            for tx in amazon_txs:
                # Sum all income lines for same order (payment + any adjustments)
                on = tx['order_number']
                amazon_map[on] = amazon_map.get(on, Decimal('0')) + tx['amount']
            # Also grab expense (fee) lines
            amazon_fees = Transaction.objects.filter(
                store=store,
                order_number__in=order_nums,
                type='expense',
            ).exclude(category='Printify Order').values('order_number', 'amount')
            fees_map = {}
            for tx in amazon_fees:
                on = tx['order_number']
                fees_map[on] = fees_map.get(on, Decimal('0')) + tx['amount']

            for row in rows:
                on = row.get('order_number', '')
                revenue  = amazon_map.get(on)
                fees     = fees_map.get(on, Decimal('0'))
                prod     = Decimal(row['amount'])
                if revenue is not None:
                    net = revenue - fees - prod
                    row['amazon_revenue']  = str(revenue)
                    row['amazon_fees']     = str(fees)
                    row['amazon_net']      = str(net)
                    row['amazon_matched']  = True
                else:
                    row['amazon_revenue']  = ''
                    row['amazon_fees']     = ''
                    row['amazon_net']      = ''
                    row['amazon_matched']  = False

        # ── Tag each row with its index so form fields work when split by matched/unmatched ──
        for i, r in enumerate(rows):
            r['row_idx'] = i

        # ── Store in session ──
        request.session[session_key] = rows
        request.session[session_key + '_meta'] = {'is_printify': is_printify, 'skipped': skipped}

        # ── Printify: show discovery step first ──
        if is_printify:
            matched_rows   = [r for r in rows if r.get('amazon_matched')]
            unmatched_rows = [r for r in rows if not r.get('amazon_matched')]
            total_revenue  = sum(Decimal(r['amazon_revenue']) for r in matched_rows)
            total_fees     = sum(Decimal(r['amazon_fees'])    for r in matched_rows)
            total_prod     = sum(Decimal(r['amount'])         for r in matched_rows)
            total_net      = total_revenue - total_fees - total_prod
            return render(request, 'vendors/import_invoices.html', {
                'store': store, 'vendors': vendors,
                'rows': rows, 'skipped': skipped,
                'preview': False, 'discovery': True,
                'is_printify': True,
                'matched_rows':    matched_rows,
                'unmatched_rows':  unmatched_rows,
                'matched_count':   len(matched_rows),
                'unmatched_count': len(unmatched_rows),
                'total_count':     len(rows),
                'total_revenue':   str(total_revenue),
                'total_fees':      str(total_fees),
                'total_prod':      str(total_prod),
                'total_net':       str(total_net),
            })

        # ── Generic CSV: go straight to preview ──
        return render(request, 'vendors/import_invoices.html', {
            'store': store, 'vendors': vendors,
            'rows': rows, 'skipped': skipped,
            'preview': True, 'discovery': False,
            'is_printify': False,
        })

    return render(request, 'vendors/import_invoices.html', {
        'store': store, 'vendors': vendors, 'preview': False, 'discovery': False,
    })
