"""Shipping/billing address book entries.

An Address belongs to exactly one User and stores a single postal destination
reused at checkout: Order.shipping_address_id points back here, so an order
copies no address text of its own and the user's book stays editable.
"""

from app import db
from datetime import datetime


# Customer's saved delivery address; many addresses per user, many orders per address.
class Address(db.Model):
    # Explicit table name so the schema matches the migration/seed SQL scripts.
    __tablename__ = 'addresses'

    id = db.Column(db.Integer, primary_key=True)
    # Owning account; nullable=False enforces that addresses cannot be orphaned.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Free-form nickname shown in the address picker, e.g. "Home" / "Office".
    label = db.Column(db.String(50))
    line1 = db.Column(db.String(200), nullable=False)
    # Optional second line (flat, landmark, suite) - only rendered when set.
    line2 = db.Column(db.String(200))
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    # ISO 3166-1 alpha-2 code, e.g. "IN" or "US"; used for currency/tax decisions.
    country = db.Column(db.String(2), nullable=False)
    postal_code = db.Column(db.String(20), nullable=False)
    # Marks the address pre-selected at checkout; the app keeps at most one default.
    is_default = db.Column(db.Boolean, default=False)
