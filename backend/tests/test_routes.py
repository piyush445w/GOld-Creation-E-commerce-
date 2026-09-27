"""HTTP-level tests for the storefront and admin blueprints.

These tests exercise the real routing stack through Flask's test client: which
URLs return 200, which redirect, and which 404. The admin cases double as
authorisation tests - they verify that ``admin_required`` hides the back-office
from anonymous visitors and from signed-in customers.

The ``client`` and ``db_session`` fixtures come from ``conftest.py``, which
provides an app bound to an isolated in-memory database per test.
"""

import pytest
from app import db
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.models.address import Address
from app.models.order import Order
from werkzeug.security import generate_password_hash


# ---- Storefront: public pages must render for anonymous shoppers -------------

class TestStorefrontRoutes:
    """Covers the anonymous, server-rendered shopping pages."""

    # The homepage must return 200 for an anonymous visitor. The `currency`
    # cookie is pre-set because the layout's context processor always resolves
    # a display currency, and these tests assert a clean render.
    def test_index_returns_200(self, client):
        client.set_cookie('localhost', 'currency', 'INR')
        resp = client.get('/')
        assert resp.status_code == 200

    # A product detail page must render for a real product. The category is
    # created first because Product.category_id is a required foreign key.
    def test_product_detail_returns_200(self, client, db_session):
        category = Category(name='Test', slug='test')
        db_session.add(category)
        db_session.commit()

        product = Product(category_id=category.id, name='Test Product', slug='test-product', base_price=100)
        db_session.add(product)
        db_session.commit()

        client.set_cookie('localhost', 'currency', 'INR')
        resp = client.get('/product/test-product')
        assert resp.status_code == 200

    # An unknown slug must 404 rather than raising a 500, so bad links and stale
    # URLs fail gracefully.
    def test_product_detail_returns_404(self, client):
        client.set_cookie('localhost', 'currency', 'INR')
        resp = client.get('/product/does-not-exist')
        assert resp.status_code == 404

    # The cart is guest-accessible and must render for anonymous shoppers
    # (guest carts are keyed by a session id rather than a user).
    def test_cart_view_returns_200(self, client):
        client.set_cookie('localhost', 'currency', 'INR')
        resp = client.get('/cart')
        assert resp.status_code == 200

    # Checkout with an empty cart must bounce the shopper away (302) instead of
    # rendering a checkout page they cannot complete.
    def test_checkout_redirects_when_empty(self, client):
        client.set_cookie('localhost', 'currency', 'INR')
        resp = client.get('/checkout')
        assert resp.status_code == 302


# ---- Admin: access control on the back-office --------------------------------

class TestAdminRoutes:
    """Covers the admin entry points and their login boundary."""

    # An anonymous visitor hitting the admin dashboard must be redirected to
    # the ADMIN login specifically, not the customer one.
    def test_dashboard_redirects_to_login(self, client):
        resp = client.get('/admin/')
        assert resp.status_code == 302
        assert '/auth/admin/login' in resp.headers.get('Location', '')

    # The admin login page itself must render. The url_for patch exists because
    # this shared page is also reachable in states where some endpoint has not
    # been registered; swallowing BuildError keeps the test about the 200.
    def test_admin_login_page_returns_200(self, app, monkeypatch):
        from werkzeug.routing import BuildError

        original_url_for = app.jinja_env.globals['url_for']

        # Fallback that returns an inert href instead of raising, so a template
        # reference to a missing endpoint cannot fail an unrelated assertion.
        def safe_url_for(endpoint, **values):
            try:
                return original_url_for(endpoint, **values)
            except BuildError:
                return '#'

        # monkeypatch reverts this automatically after the test.
        monkeypatch.setitem(app.jinja_env.globals, 'url_for', safe_url_for)

        with app.test_client() as client:
            resp = client.get('/auth/admin/login')
            assert resp.status_code == 200

# Order-management screens and their authorisation boundary. The two helper
# methods build the fixtures the tests share: one admin, and one customer
# owning two orders in different states (pending and paid) so the status
# filter has something to discriminate.
class TestAdminOrders:
    """Covers the admin orders list, filter, detail view, and access control."""

    # Creates the admin account used to sign in via /auth/admin/login.
    def _create_admin(self, db_session):
        admin = User(
            name='Admin User',
            email='admin@test.com',
            password_hash=generate_password_hash('admin123'),
            role='admin',
        )
        db_session.add(admin)
        db_session.commit()
        return admin

    # Creates a customer, their address (orders require one), and two orders:
    # ORD001 pending, ORD002 paid. Returns the pair so tests can assert on ids.
    def _create_customer_and_orders(self, db_session):
        customer = User(
            name='Test Customer',
            email='customer@test.com',
            password_hash=generate_password_hash('pass123'),
            role='customer',
        )
        db_session.add(customer)
        db_session.commit()

        address = Address(
            user_id=customer.id,
            line1='123 Main St',
            city='City',
            state='State',
            country='IN',
            postal_code='12345',
        )
        db_session.add(address)
        db_session.commit()

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
        db_session.add(order1)
        db_session.add(order2)
        db_session.commit()
        return order1, order2

    # Anonymous access to the orders list must redirect to the admin login.
    def test_orders_redirects_when_unauthenticated(self, client):
        resp = client.get('/admin/orders')
        assert resp.status_code == 302
        assert '/auth/admin/login' in resp.headers.get('Location', '')

    # A signed-in admin sees the orders list, and the rendered HTML must contain
    # the customer's name and both order statuses.
    def test_orders_returns_200_for_admin(self, client, db_session):
        self._create_admin(db_session)
        self._create_customer_and_orders(db_session)
        client.post('/auth/admin/login', data={
            'email': 'admin@test.com',
            'password': 'admin123',
        })
        resp = client.get('/admin/orders')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Test Customer' in html
        assert 'Pending' in html
        assert 'Paid' in html

    # The ?status= filter must be accepted and still render the list.
    def test_orders_status_filter(self, client, db_session):
        self._create_admin(db_session)
        self._create_customer_and_orders(db_session)
        client.post('/auth/admin/login', data={
            'email': 'admin@test.com',
            'password': 'admin123',
        })
        resp = client.get('/admin/orders?status=paid')
        assert resp.status_code == 200

    # A signed-in CUSTOMER must be refused. admin_required redirects to the
    # admin login (302) rather than leaking the back-office with a 404.
    def test_orders_denied_for_non_admin(self, client, db_session):
        self._create_customer_and_orders(db_session)
        client.post('/auth/login', data={
            'email': 'customer@test.com',
            'password': 'pass123',
        })
        resp = client.get('/admin/orders')
        assert resp.status_code == 302
        assert '/auth/admin/login' in resp.headers.get('Location', '')

    # The per-order detail screen must load for an authenticated admin.
    def test_order_detail_for_admin(self, client, db_session):
        self._create_admin(db_session)
        orders = self._create_customer_and_orders(db_session)
        order1 = orders[0]
        client.post('/auth/admin/login', data={
            'email': 'admin@test.com',
            'password': 'admin123',
        })
        resp = client.get(f'/admin/orders/{order1.id}')
        assert resp.status_code == 200
