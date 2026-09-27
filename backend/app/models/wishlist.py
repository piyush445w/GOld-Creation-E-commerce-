"""Saved-for-later ("wishlist") products.

Like CartItem, WishlistItem works for both signed-in users (user_id) and guests
(guest_session_id), so shoppers can save items before registering; the guest
entries are claimed on sign-in. It records interest only - no price, stock, or
quantity is captured, and a Product is referenced rather than copied.
"""

from app import db
from datetime import datetime


# One product saved to a customer's (or guest's) wishlist.
class WishlistItem(db.Model):
    __tablename__ = 'wishlist_items'

    id = db.Column(db.Integer, primary_key=True)
    # Owner account; NULL while the entry belongs to a guest session.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    # The saved product; the entry disappears with the product itself.
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    # Anonymous session identifier used to find a guest's wishlist.
    guest_session_id = db.Column(db.String(100), nullable=True)
    # When the item was saved; used to order the wishlist page most-recent-first.
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
