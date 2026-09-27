"""ORM-level tests for the SQLAlchemy models and their relationships.

These tests bypass HTTP entirely and drive ``db_session`` directly (provided by
``conftest.py`` on an isolated in-memory database). They cover two things the
store depends on:

1. Column defaults and types - notably ``Order.status`` defaulting to
   ``'pending'``, which the fulfilment workflow relies on.
2. Relationship wiring - every ``lazy='dynamic'`` association that the routes
   traverse (user -> orders, category -> products, product -> media/reviews,
   order -> items, cart item -> variant -> product) is asserted, so a broken
   backref fails here rather than as a 500 in production.
"""

import pytest
from app import db
from app.models.user import User
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.product_media import ProductMedia
from app.models.cart import CartItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.address import Address
from app.models.review import Review


# ---- User: identity root of the order and cart graphs ------------------------

class TestUser:
    """Account persistence and the user -> orders / user -> cart links."""

    # A user row must persist with a generated id and the values assigned.
    def test_create_user(self, db_session):
        user = User(name='Test User', email='test@example.com', password_hash='hash123', role='customer')
        db_session.add(user)
        db_session.commit()
        assert user.id is not None
        assert user.name == 'Test User'
        assert user.email == 'test@example.com'
        assert user.role == 'customer'

    # user.orders is a dynamic relationship, so it must expose .count()/.first()
    # and resolve the order created against this user's id.
    def test_user_orders_relationship(self, db_session):
        user = User(name='Test', email='test@example.com', password_hash='hash', role='customer')
        db_session.add(user)
        db_session.commit()

        # An order cannot exist without a shipping address (NOT NULL FK).
        address = Address(user_id=user.id, line1='123 Main St', city='City', state='State', country='IN', postal_code='12345')
        db_session.add(address)
        db_session.commit()

        order = Order(user_id=user.id, order_number='ORD123', subtotal=100, total=100, charged_amount=100, shipping_address_id=address.id)
        db_session.add(order)
        db_session.commit()

        assert user.orders.count() == 1
        assert user.orders.first().order_number == 'ORD123'

    # Walks the full cart chain user -> cart_items -> variant -> product, which
    # is the traversal the cart view performs to price a line.
    def test_user_cart_items_relationship(self, db_session):
        user = User(name='Test', email='test@example.com', password_hash='hash', role='customer')
        db_session.add(user)
        db_session.commit()

        category = Category(name='Test', slug='test')
        db_session.add(category)
        db_session.commit()

        product = Product(category_id=category.id, name='Product', slug='product', base_price=100)
        db_session.add(product)
        db_session.commit()

        variant = ProductVariant(product_id=product.id, stock_quantity=10)
        db_session.add(variant)
        db_session.commit()

        cart_item = CartItem(user_id=user.id, product_variant_id=variant.id, quantity=1)
        db_session.add(cart_item)
        db_session.commit()

        assert user.cart_items.count() == 1
        assert user.cart_items.first().variant.product.name == 'Product'


# ---- Category: taxonomy root --------------------------------------------------

class TestCategory:
    """Category persistence and the category -> products backref."""

    # A category row must persist with a generated id.
    def test_create_category(self, db_session):
        category = Category(name='Jewelry', slug='jewelry')
        db_session.add(category)
        db_session.commit()
        assert category.id is not None
        assert category.name == 'Jewelry'
        assert category.slug == 'jewelry'

    # category.products is dynamic and is what the storefront listing filters on.
    def test_category_products_relationship(self, db_session):
        category = Category(name='Jewelry', slug='jewelry')
        db_session.add(category)
        db_session.commit()

        product = Product(category_id=category.id, name='Ring', slug='ring', base_price=500)
        db_session.add(product)
        db_session.commit()

        assert category.products.count() == 1
        assert category.products.first().name == 'Ring'


# ---- Product: catalogue root of media, variants and reviews ------------------

class TestProduct:
    """Product persistence and its media / review collections."""

    # A product requires a category FK; assert the row persists with its price.
    def test_create_product(self, db_session):
        category = Category(name='Test', slug='test')
        db_session.add(category)
        db_session.commit()

        product = Product(category_id=category.id, name='Gold Ring', slug='gold-ring', base_price=1000)
        db_session.add(product)
        db_session.commit()
        assert product.id is not None
        assert product.name == 'Gold Ring'
        assert product.base_price == 1000

    # product.media drives the product gallery; the image/video discriminator
    # lives in media_type.
    def test_product_media_relationship(self, db_session):
        category = Category(name='Test', slug='test')
        db_session.add(category)
        db_session.commit()

        product = Product(category_id=category.id, name='Ring', slug='ring', base_price=500)
        db_session.add(product)
        db_session.commit()

        media = ProductMedia(product_id=product.id, media_type='image', media_url='/uploads/ring.jpg')
        db_session.add(media)
        db_session.commit()

        assert product.media.count() == 1
        assert product.media.first().media_url == '/uploads/ring.jpg'

    # product.reviews backs both the rating summary and the review form; the
    # (product, user) pair is unique, which is why only one row is added.
    def test_product_reviews_relationship(self, db_session):
        category = Category(name='Test', slug='test')
        db_session.add(category)
        db_session.commit()

        product = Product(category_id=category.id, name='Ring', slug='ring', base_price=500)
        db_session.add(product)
        db_session.commit()

        user = User(name='Reviewer', email='reviewer@example.com', password_hash='hash', role='customer')
        db_session.add(user)
        db_session.commit()

        review = Review(product_id=product.id, user_id=user.id, rating=5, comment='Great!')
        db_session.add(review)
        db_session.commit()

        assert product.reviews.count() == 1
        assert product.reviews.first().rating == 5


# ---- ProductMedia: gallery assets -------------------------------------------

class TestProductMedia:
    """Standalone persistence check for a gallery asset."""

    # Media rows must persist with the declared media_type, which the gallery
    # uses to decide between an <img> and a <video> element.
    def test_create_product_media(self, db_session):
        category = Category(name='Test', slug='test')
        db_session.add(category)
        db_session.commit()

        product = Product(category_id=category.id, name='Ring', slug='ring', base_price=500)
        db_session.add(product)
        db_session.commit()

        media = ProductMedia(product_id=product.id, media_type='image', media_url='/uploads/ring.jpg')
        db_session.add(media)
        db_session.commit()
        assert media.id is not None
        assert media.media_type == 'image'


# ---- CartItem: the purchasable unit is the variant, not the product ----------

class TestCartItem:
    """Cart lines and the cart -> variant -> product chain."""

    # A cart line is created against a variant (no user_id here, which models a
    # guest cart) and stores the chosen quantity.
    def test_create_cart_item(self, db_session):
        category = Category(name='Test', slug='test')
        db_session.add(category)
        db_session.commit()

        product = Product(category_id=category.id, name='Ring', slug='ring', base_price=500)
        db_session.add(product)
        db_session.commit()

        variant = ProductVariant(product_id=product.id, stock_quantity=10)
        db_session.add(variant)
        db_session.commit()

        cart_item = CartItem(product_variant_id=variant.id, quantity=2)
        db_session.add(cart_item)
        db_session.commit()
        assert cart_item.id is not None
        assert cart_item.quantity == 2

    # Asserts the convenience backref used to render a cart line's product name.
    def test_cart_item_variant_relationship(self, db_session):
        category = Category(name='Test', slug='test')
        db_session.add(category)
        db_session.commit()

        product = Product(category_id=category.id, name='Ring', slug='ring', base_price=500)
        db_session.add(product)
        db_session.commit()

        variant = ProductVariant(product_id=product.id, stock_quantity=10)
        db_session.add(variant)
        db_session.commit()

        cart_item = CartItem(product_variant_id=variant.id, quantity=1)
        db_session.add(cart_item)
        db_session.commit()

        assert cart_item.variant.product.name == 'Ring'


# ---- Order: financial header and its line items -----------------------------

class TestOrder:
    """Order creation defaults and the order -> items relationship."""

    # Verifies the column default: a freshly created order is 'pending', which
    # is the entry point of the fulfilment status machine.
    def test_create_order(self, db_session):
        user = User(name='Test', email='test@example.com', password_hash='hash', role='customer')
        db_session.add(user)
        db_session.commit()

        address = Address(user_id=user.id, line1='123 Main St', city='City', state='State', country='IN', postal_code='12345')
        db_session.add(address)
        db_session.commit()

        order = Order(user_id=user.id, order_number='ORD001', subtotal=100, total=100, charged_amount=100, shipping_address_id=address.id)
        db_session.add(order)
        db_session.commit()
        assert order.id is not None
        assert order.status == 'pending'

    # order.items is dynamic. The line stores *snapshots* of the product name and
    # unit price rather than reading them live, so historical invoices stay
    # correct after the catalogue changes - hence the snapshot assertions.
    def test_order_items_relationship(self, db_session):
        user = User(name='Test', email='test@example.com', password_hash='hash', role='customer')
        db_session.add(user)
        db_session.commit()

        address = Address(user_id=user.id, line1='123 Main St', city='City', state='State', country='IN', postal_code='12345')
        db_session.add(address)
        db_session.commit()

        category = Category(name='Test', slug='test')
        db_session.add(category)
        db_session.commit()

        product = Product(category_id=category.id, name='Ring', slug='ring', base_price=500)
        db_session.add(product)
        db_session.commit()

        variant = ProductVariant(product_id=product.id, stock_quantity=10)
        db_session.add(variant)
        db_session.commit()

        order = Order(user_id=user.id, order_number='ORD001', subtotal=500, total=500, charged_amount=500, shipping_address_id=address.id)
        db_session.add(order)
        db_session.commit()

        order_item = OrderItem(order_id=order.id, product_variant_id=variant.id, product_name_snapshot='Ring', unit_price_snapshot=500, quantity=1, subtotal=500)
        db_session.add(order_item)
        db_session.commit()

        assert order.items.count() == 1
        assert order.items.first().product_name_snapshot == 'Ring'


# ---- Review: customer ratings ------------------------------------------------

class TestReview:
    """Standalone persistence check for a customer review."""

    # A review must persist with its rating; the admin moderation queue and the
    # product rating average both read these rows.
    def test_create_review(self, db_session):
        user = User(name='Reviewer', email='reviewer@example.com', password_hash='hash', role='customer')
        db_session.add(user)
        db_session.commit()

        category = Category(name='Test', slug='test')
        db_session.add(category)
        db_session.commit()

        product = Product(category_id=category.id, name='Ring', slug='ring', base_price=500)
        db_session.add(product)
        db_session.commit()

        review = Review(product_id=product.id, user_id=user.id, rating=5, comment='Excellent')
        db_session.add(review)
        db_session.commit()
        assert review.id is not None
        assert review.rating == 5

