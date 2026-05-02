import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum

from .models import BankAccount, BankTransaction, ACCOUNT_TYPE_CHOICES


# ── helpers ─────────────────────────────────────────────────────────────────

def _parse_amount(s):
    if not s:
        return None
    s = s.strip().replace('$', '').replace(',', '').replace(' ', '')
    if not s or s in ('-', '+'):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _parse_date(s):
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y', '%d/%m/%Y', '%m-%d-%Y', '%Y/%m/%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _detect_columns(headers):
    h = [c.strip().lower() for c in headers]

    def find(*names):
        for n in names:
            for i, col in enumerate(h):
                if n in col:
                    return i
        return None

    return {
        'date':    find('transaction date', 'trans date', 'posted date', 'date'),
        'desc':    find('description', 'memo', 'narrative', 'payee', 'details', 'name'),
        'amount':  find('amount'),
        'credit':  find('credit', 'deposits', 'deposit', 'money in'),
        'debit':   find('debit', 'withdrawal', 'withdrawals', 'money out'),
        'balance': find('running bal', 'balance', 'ledger'),
    }


# ── views ────────────────────────────────────────────────────────────────────

def account_list(request):
    accounts = BankAccount.objects.filter(active=True)
    for acc in accounts:
        txs = acc.transactions.all()
        acc.stat_credits  = txs.filter(type='credit').aggregate(t=Sum('amount'))['t'] or 0
        acc.stat_debits   = txs.filter(type='debit').aggregate(t=Sum('amount'))['t'] or 0
        acc.stat_net      = acc.stat_credits - acc.stat_debits
        acc.stat_tx_count = txs.count()
    return render(request, 'banking/list.html', {'accounts': accounts})


def account_detail(request, pk):
    account = get_object_or_404(BankAccount, pk=pk)
    transactions = account.transactions.order_by('-date', '-created_at')
    credits  = transactions.filter(type='credit').aggregate(t=Sum('amount'))['t'] or 0
    debits   = transactions.filter(type='debit').aggregate(t=Sum('amount'))['t'] or 0
    net      = credits - debits
    import_created = request.session.pop(f'bank_import_success_{pk}', None)
    import_dupes   = request.session.pop(f'bank_import_dupes_{pk}', None)
    return render(request, 'banking/account_detail.html', {
        'account':        account,
        'transactions':   transactions,
        'credits':        credits,
        'debits':         debits,
        'net':            net,
        'tx_count':       transactions.count(),
        'import_created': import_created,
        'import_dupes':   import_dupes,
    })


def add_account(request):
    if request.method == 'POST':
        name         = request.POST.get('name', '').strip()
        bank_name    = request.POST.get('bank_name', '').strip()
        account_type = request.POST.get('account_type', 'checking')
        last4        = request.POST.get('last4', '').strip()[:4]
        if name and account_type in dict(ACCOUNT_TYPE_CHOICES):
            BankAccount.objects.create(
                name=name,
                bank_name=bank_name,
                account_type=account_type,
                last4=last4,
            )
            return redirect('account_list')
    return render(request, 'banking/add_account.html', {
        'account_types': ACCOUNT_TYPE_CHOICES,
    })


def delete_account(request, pk):
    account = get_object_or_404(BankAccount, pk=pk)
    if request.method == 'POST':
        account.delete()
    return redirect('account_list')


# ── CSV import ───────────────────────────────────────────────────────────────

def import_statement(request, pk):
    account = get_object_or_404(BankAccount, pk=pk)

    if request.method == 'POST' and request.FILES.get('csv_file'):
        raw = request.FILES['csv_file'].read().decode('utf-8-sig', errors='replace')
        reader = csv.reader(io.StringIO(raw))
        rows = [r for r in reader]

        if not rows:
            error = 'The uploaded file is empty.'
            return render(request, 'banking/import_statement.html', {'account': account, 'error': error})

        # find the header row (first row that mentions date/amount/debit/credit)
        header_idx = 0
        for i, row in enumerate(rows[:6]):
            joined = ' '.join(row).lower()
            if any(w in joined for w in ('date', 'amount', 'debit', 'credit', 'balance', 'description')):
                header_idx = i
                break

        headers  = rows[header_idx]
        mapping  = _detect_columns(headers)
        data_rows = rows[header_idx + 1:]

        parsed  = []
        skipped = 0

        for row in data_rows:
            if not any(cell.strip() for cell in row):
                continue  # blank row

            # date
            date_val = None
            if mapping['date'] is not None and mapping['date'] < len(row):
                date_val = _parse_date(row[mapping['date']])
            if date_val is None:
                skipped += 1
                continue

            # description
            desc = ''
            if mapping['desc'] is not None and mapping['desc'] < len(row):
                desc = row[mapping['desc']].strip()

            # balance
            balance = None
            if mapping['balance'] is not None and mapping['balance'] < len(row):
                balance = _parse_amount(row[mapping['balance']])

            # amount + type
            if mapping['amount'] is not None and mapping['amount'] < len(row):
                amt = _parse_amount(row[mapping['amount']])
                if amt is None:
                    skipped += 1
                    continue
                tx_type = 'credit' if amt >= 0 else 'debit'
                amt = abs(amt)
            elif mapping['credit'] is not None or mapping['debit'] is not None:
                credit_v = None
                debit_v  = None
                if mapping['credit'] is not None and mapping['credit'] < len(row):
                    credit_v = _parse_amount(row[mapping['credit']])
                if mapping['debit'] is not None and mapping['debit'] < len(row):
                    debit_v = _parse_amount(row[mapping['debit']])
                if credit_v and credit_v > 0:
                    amt, tx_type = credit_v, 'credit'
                elif debit_v and debit_v > 0:
                    amt, tx_type = debit_v, 'debit'
                else:
                    skipped += 1
                    continue
            else:
                skipped += 1
                continue

            parsed.append({
                'date':         str(date_val),
                'description':  desc,
                'amount':       str(amt),
                'type':         tx_type,
                'balance_after': str(balance) if balance is not None else '',
            })

        if not parsed:
            error = f'No valid rows found. {skipped} row(s) skipped (bad date/amount).'
            return render(request, 'banking/import_statement.html', {'account': account, 'error': error})

        request.session[f'bank_import_{pk}'] = parsed
        return render(request, 'banking/import_preview.html', {
            'account': account,
            'rows':    parsed[:200],
            'total':   len(parsed),
            'skipped': skipped,
        })

    return render(request, 'banking/import_statement.html', {'account': account})


def import_confirm(request, pk):
    account = get_object_or_404(BankAccount, pk=pk)
    if request.method != 'POST':
        return redirect('import_statement', pk=pk)

    parsed = request.session.pop(f'bank_import_{pk}', [])
    if not parsed:
        return redirect('import_statement', pk=pk)

    created = 0
    skipped_dupes = 0
    for row in parsed:
        date_val = _parse_date(row['date'])
        if not date_val:
            continue
        amt = _parse_amount(row['amount'])
        if amt is None:
            continue
        balance = _parse_amount(row.get('balance_after', ''))
        _, was_created = BankTransaction.objects.get_or_create(
            account=account,
            date=date_val,
            description=row['description'],
            amount=amt,
            type=row['type'],
            defaults={'balance_after': balance},
        )
        if was_created:
            created += 1
        else:
            skipped_dupes += 1

    request.session[f'bank_import_success_{pk}'] = created
    request.session[f'bank_import_dupes_{pk}'] = skipped_dupes
    return redirect('account_detail', pk=pk)
