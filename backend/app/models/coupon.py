"""Promotional discount codes applied at checkout.

A Coupon stores either a percentage or fixed-amount discount plus the
eligibility rules the checkout service enforces: minimum order value, a
validity window, a total usage cap, and an optional category scope so a
promo can be restricted to a single collection.
"""

from app import db
from sqlalchemy import Numeric
from datetime import datetime


# A discount code and the conditions under which it may be redeemed.
class Coupon(db.Model):
    __tablename__ = 'coupons'

    id = db.Column(db.Integer, primary_key=True)
    # Unique code the customer types in; looked up case-insensitively at checkout.
    code = db.Column(db.String(50), unique=True, nullable=False)
    # Discount kind - 'percentage' or 'fixed' - matched against discount_value.
    discount_type = db.Column(db.String(10), nullable=False)
    # Amount or percent; Numeric keeps money arithmetic exact (no float drift).
    discount_value = db.Column(Numeric(10, 2), nullable=False)
    # Cart subtotal threshold the order must meet for the code to validate.
    min_order_value = db.Column(Numeric(10, 2), default=0)
    # Redemption window; either bound may be NULL for an open-ended code.
    valid_from = db.Column(db.DateTime)
    valid_to = db.Column(db.DateTime)
    # Maximum total redemptions; NULL means unlimited.
    usage_limit = db.Column(db.Integer)
    # Running redemption counter checked against usage_limit when a code is applied.
    times_used = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    # When set, the discount applies only to products in this category.
    applies_to_category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)

    # Convenience link used by validation code to read the scoped category.
    category = db.relationship('Category', backref='coupons')
