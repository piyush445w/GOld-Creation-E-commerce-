"""Debug script to reproduce the 500 error on order placement."""
import os
import sys

os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))

from app import create_app, db
from app.models.user import User
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.cart import CartItem
from app.models.address import Address
from app.models.currency import Currency
from werkzeug.security import generate_password_hash

app = create_app('testing')
with app.app_context():
    db.create_all()
    
    # Create currency
    inr = Currency(code='INR', symbol='INR', exchange_rate_to_inr=1.0, is_settlement_enabled=True)
    usd = Currency(code='USD', symbol='$', exchange_rate_to_inr=83.0, is_settlement_enabled=True)
    db.session.add_all([inr, usd])
    db.session.commit()
    
    # Create user
    user = User(
        name='Test User',
        email='test@example.com',
        password_hash=generate_password_hash('password'),
        role='customer'
    )
    db.session.add(user)
    db.session.commit()
    
    # Create category and product
    category = Category(name='Test', slug='test')
    db.session.add(category)
    db.session.commit()
    
    product = Product(category_id=category.id, name='Test Product', slug='test-product', base_price=100)
    db.session.add(product)
    db.session.commit()
    
    # Create variant
    variant = ProductVariant(product_id=product.id, size='M', color='Red', price_override=100, stock_quantity=10)
    db.session.add(variant)
    db.session.commit()
    
    # Create cart item
    cart_item = CartItem(user_id=user.id, product_variant_id=variant.id, quantity=1)
    db.session.add(cart_item)
    db.session.commit()
    
    # Simulate placing an order
    with app.test_client() as client:
        # Login first
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
        
        # Set currency cookie
        client.set_cookie('localhost', 'currency', 'INR')
        
        # Place order
        response = client.post('/checkout/place-order', data={
            'line1': '123 Main St',
            'city': 'City',
            'state': 'State',
            'country': 'IN',
            'postal_code': '12345',
            'payment_method': 'cod',
        })
        
        print(f"Status code: {response.status_code}")
        print(f"Location: {response.headers.get('Location')}")
        if response.status_code >= 400:
            print(f"Response data: {response.data.decode('utf-8')[:500]}")
        else:
            print("Order placed successfully!")
