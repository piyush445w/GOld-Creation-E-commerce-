"""Shopping cart line items.

A CartItem is a quantity of one ProductVariant. It supports two shopper types:
a logged-in customer (user_id set) and an anonymous visitor tracked by an
anonymous session cookie (guest_session_id), which is how carts survive before
login and are merged on sign-in.
"""

from app import db
from datetime import datetime


# One line in a customer's (or guest's) active cart.
class CartItem(db.Model):
    __tablename__ = 'cart_items'

    id = db.Column(db.Integer, primary_key=True)
    # Set for logged-in shoppers; NULL while the cart belongs to a guest session.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    # Anonymous session identifier used to find the cart of a not-yet-signed-in visitor.
    guest_session_id = db.Column(db.String(100))
    # The exact purchasable unit (product + size/color); stock lives on the variant.
    product_variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=False)
    # Units requested; validated against variant.stock_quantity at checkout.
    quantity = db.Column(db.Integer, nullable=False, default=1)
    # Timestamp used to restore cart ordering and expire abandoned carts.
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
