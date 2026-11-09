import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'carwash_backend.settings')
django.setup()

from carwash.models import CarWash

count = 0
for w in CarWash.objects.all():
    if w.payment_method == 'CASH':
        w.cash_amount = w.total_amount
        w.mpesa_amount = 0
    elif w.payment_method == 'MPESA':
        w.cash_amount = 0
        w.mpesa_amount = w.total_amount
    w.save()
    count += 1

print(f"Successfully backfilled {count} washes with cash and mpesa amounts.")

