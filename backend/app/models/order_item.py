"""Purchased line items within an order.

Each OrderItem records the ProductVariant bought plus snapshot copies of the
product name and unit price. The snapshots deliberately duplicate mutable
catalogue data so historical invoices, returns, and reports stay correct after
a product is renamed or repriced.
"""

from app import db
from sqlalchemy import Numeric
from datetime import datetime


# One product/quantity line on an order, with frozen product details.
class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    # Parent order header; cascade of ownership is handled by the Order relationship.
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    # The exact size/color bought; still linked for stock, returns, and re-orders.
    product_variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=False)
    # Product name copied at purchase time, so later catalogue edits don't rewrite history.
    product_name_snapshot = db.Column(db.String(200), nullable=False)
    # Unit price at purchase time in the order's display currency.
    unit_price_snapshot = db.Column(Numeric(10, 2), nullable=False)
    # Units purchased on this line; drives return quantities and fulfilment counts.
    quantity = db.Column(db.Integer, nullable=False)
    # unit_price_snapshot * quantity, summed into Order.subtotal at checkout.
    subtotal = db.Column(Numeric(10, 2), nullable=False)
