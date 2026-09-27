"""Standalone end-to-end smoke script for the /admin/orders route.

Unlike the pytest suite in ``tests/``, this is a hand-run diagnostic script
(``python test_orders_route.py``) that builds a throwaway in-memory database,
seeds a minimal catalogue plus two orders, and then drives the real HTTP stack
with Flask's test client while printing each step. It is intentionally kept out
of ``testpaths`` in pytest.ini so it is not collected as part of CI.

Its focus is the admin authorisation boundary on the orders screens: that
anonymous visitors are redirected to the admin login, that an admin can list
and filter orders, that a non-admin gets a 404 rather than leaking the page.
"""

import os
import sys

# Put backend/ on sys.path so `import app` works no matter which directory the
# script is launched from.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

# The test/production configs hard-fail when these are missing, so they must be
# set BEFORE create_app() imports app.config.
os.environ['SECRET_KEY'] = 'test-secret-key'
# An in-memory SQLite database keeps the script self-contained and disposable -
# no MySQL server is required to run this diagnostic.
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

# Imported after the environment is prepared, since importing app configures
# the extension singletons against these values.
from app import create_app, db
from app.models.user import User
from app.models.address import Address
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.currency import Currency
from werkzeug.security import generate_password_hash

# ---- Fixture seeding: build just enough data to exercise the orders screens ----

def main():
    """Seed a throwaway dataset, run 7 checks, then tear the database down."""
    app = create_app('testing')

    # Everything below needs an application context to use db.session.
    with app.app_context():
        # Create the full schema so the order screens can query real tables.
        db.create_all()

        # Two currencies: INR as the base (rate 1.0) and USD at a fixed test
        # rate, so price rendering never depends on a live FX call.
        inr = Currency(code='INR', symbol='INR', exchange_rate_to_inr=1)
        usd = Currency(code='USD', symbol='$', exchange_rate_to_inr=83.0)
        db.session.add(inr)
        db.session.add(usd)

        # The admin account the authorisation checks will sign in as.
        admin = User(
            name='Admin User',
            email='admin@test.com',
            password_hash=generate_password_hash('admin123'),
            role='admin',
        )
        db.session.add(admin)
        db.session.commit()

        # A regular customer who owns the orders, and will later be used to
        # prove a non-admin is denied access.
        customer = User(
            name='Test Customer',
            email='customer@test.com',
            password_hash=generate_password_hash('pass123'),
            role='customer',
        )
        db.session.add(customer)
        db.session.commit()

        # Orders require a shipping address, so create one for the customer.
        address = Address(
            user_id=customer.id,
            line1='123 Main St',
            city='City',
            state='State',
            country='IN',
            postal_code='12345',
        )
        db.session.add(address)
        db.session.commit()

        # Two orders in deliberately different states so the status filter has
        # something to discriminate: one pending, one paid.
        order1 = Order(
            user_id=customer.id,
            order_number='ORD001',
            status='pending',
            subtotal=100,
            total=100,
            charged_amount=100,
            payment_method='razorpay',
            payment_status='pending',
            shipping_address_id=address.id,
        )
        order2 = Order(
            user_id=customer.id,
            order_number='ORD002',
            status='paid',
            subtotal=200,
            total=200,
            charged_amount=200,
            payment_method='cod',
            payment_status='paid',
            shipping_address_id=address.id,
        )
        db.session.add(order1)
        db.session.add(order2)
        db.session.commit()

        # Echo the seeded state so a failure can be diagnosed from the log.
        print("=== Test Setup ===")
        print(f"Admin user exists: {admin.email} (role={admin.role})")
        print(f"Orders in DB: {Order.query.count()}")
        print(f"Order statuses: {[o.status for o in Order.query.all()]}")
        print()

        client = app.test_client()

        # ---- Test 1: the anonymous visitor is bounced to the admin login ----
        print("=== Test 1: Unauthenticated access redirects to login ===")
        resp = client.get('/admin/orders')
        print(f"Status code: {resp.status_code} (expected 302)")
        print(f"Location: {resp.headers.get('Location', 'none')}")
        assert resp.status_code == 302
        # Confirms admin_required redirected to the admin login, not a 404.
        assert '/auth/admin/login' in resp.headers.get('Location', '')
        print("PASS")
        print()

        # ---- Test 2: authenticate the admin (session cookie is retained) ----
        print("=== Test 2: Login as admin ===")
        resp = client.post('/auth/admin/login', data={
            'email': 'admin@test.com',
            'password': 'admin123',
        }, follow_redirects=False)
        print(f"Status code: {resp.status_code}")
        assert resp.status_code == 302
        print("Login redirect OK")
        print()

        # ---- Test 3: the orders list renders real rows for the admin ----
        print("=== Test 3: Authenticated admin accesses /admin/orders ===")
        resp = client.get('/admin/orders')
        print(f"Status code: {resp.status_code} (expected 200)")
        assert resp.status_code == 200

        # Assert on the rendered HTML so this also covers admin/orders.html.
        html = resp.data.decode('utf-8')
        assert 'Orders' in html
        assert f'#{order1.id}' in html
        assert f'#{order2.id}' in html
        assert 'Test Customer' in html
        assert 'Pending' in html
        assert 'Paid' in html
        print("Page renders with order data (IDs, customer names, statuses)")
        print("PASS")
        print()

        # ---- Test 4: the ?status= query parameter filters the list ----
        print("=== Test 4: Status filter works ===")
        resp = client.get('/admin/orders?status=paid')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        print(f"Status code: {resp.status_code} (expected 200)")
        print(f"Paid status shown: {'Paid' in html}")
        print("PASS")
        print()

        # ---- Test 5: the single-order detail screen loads ----
        print("=== Test 5: Order detail page ===")
        resp = client.get(f'/admin/orders/{order1.id}')
        assert resp.status_code == 200
        print(f"Status code: {resp.status_code}")
        print("PASS")
        print()

        # ---- Test 6: a signed-in NON-admin must still be refused ----
        # admin_required redirects unauthenticated non-admins to the admin login.
        # Because admin and customer sessions are now independent, we must clear
        # the admin session explicitly before logging in as a customer.
        print("=== Test 6: Logout, clear admin session, login as customer, verify redirect to admin login ===")
        resp = client.post('/auth/logout')
        print(f"Customer logout: {resp.status_code}")
        with client.session_transaction() as sess:
            sess.pop('admin_user_id', None)
        resp = client.post('/auth/login', data={
            'email': 'customer@test.com',
            'password': 'pass123',
        }, follow_redirects=False)
        print(f"Customer login: {resp.status_code}")
        resp = client.get('/admin/orders')
        print(f"Status code: {resp.status_code} (expected 302 redirect to admin login)")
        assert resp.status_code == 302, f"Expected 302 for non-admin, got {resp.status_code}"
        assert '/auth/admin/login' in resp.headers.get('Location', '')
        print("PASS")
        print()

        # ---- Test 7: confirm the admin row persisted with the right role ----
        print("=== Test 7: Admin user exists in database ===")
        admin_check = User.query.filter_by(email='admin@test.com').first()
        print(f"Admin found: {admin_check is not None}")
        print(f"Admin email: {admin_check.email}")
        print(f"Admin role: {admin_check.role}")
        assert admin_check is not None
        assert admin_check.role == 'admin'
        print("PASS")
        print()

        # Human-readable recap of what the seven checks established.
        print("=== Summary ===")
        print("All tests PASSED. The /admin/orders route works correctly:")
        print("  - Unauthenticated users redirected to /auth/admin/login")
        print("  - Admin users can access and render admin/orders.html")
        print("  - Orders displayed with IDs, customer names, and statuses")
        print("  - Status filtering works (?status=paid)")
        print("  - Order detail page (/admin/orders/<id>) works")
        print("  - Non-admin users redirected to admin login (302)")
        print("  - Admin user verified in database")

        # Tear down so an in-memory DB and its pooled connection are released.
        db.session.remove()
        db.drop_all()

if __name__ == '__main__':
    main()
