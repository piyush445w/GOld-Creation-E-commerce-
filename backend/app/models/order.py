"""Order header - the financial and fulfilment record of a purchase.

One Order aggregates OrderItem lines, points at the Address it ships to, and
snapshots the currency the shopper browsed in, the currency actually charged,
and the exact FX rate used. Keeping charged_amount/rate on the row makes
reconciliation and refund maths reproducible after rates move.
"""

from app import db
from sqlalchemy import Numeric
from datetime import datetime


# A placed order: totals, payment state, shipping target, and fulfilment data.
class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    # Nullable so guest checkout orders are allowed; set when a customer signs in.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    # Public human-facing reference (e.g. "GC-2026-000123") shown to support/shipping.
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    # Fulfilment lifecycle: pending -> confirmed -> shipped -> delivered (etc.).
    status = db.Column(db.String(20), default='pending')
    # Sum of line subtotals before any discount; the basis for coupon validation.
    subtotal = db.Column(Numeric(10, 2), nullable=False)
    # Value of the applied Coupon, stored so invoices stay stable if the code changes.
    discount_amount = db.Column(Numeric(10, 2), default=0)
    # Flat-rate shipping fee in the display currency.
    shipping_fee = db.Column(Numeric(10, 2), default=0)
    # Final amount in the display currency: subtotal - discount + shipping.
    total = db.Column(Numeric(10, 2), nullable=False)
    # Currency the shopper browsed in; drives how the order is shown to them.
    display_currency = db.Column(db.String(3), default='INR')
    # Currency actually debited from the customer, which may differ from display.
    charged_currency = db.Column(db.String(3), default='INR')
    # Total converted into charged_currency; the figure sent to the payment gateway.
    charged_amount = db.Column(Numeric(10, 2), nullable=False)
    # FX rate captured at checkout, so the conversion can be re-verified in audits.
    exchange_rate_used = db.Column(Numeric(10, 6), default=1)
    # Chosen rail (card, UPI, netbanking, COD) recorded for reconciliation.
    payment_method = db.Column(db.String(50))
    # Payment state (pending/paid/failed/refunded) updated by gateway callbacks.
    payment_status = db.Column(db.String(20), default='pending')
    # Gateway's own order reference, used to match webhooks and refunds.
    gateway_order_id = db.Column(db.String(100))
    # Delivery address snapshot source; required so every order ships somewhere.
    shipping_address_id = db.Column(db.Integer, db.ForeignKey('addresses.id'), nullable=False)
    # Courier tracking number, surfaced to the customer once shipped.
    tracking_number = db.Column(db.String(100))
    # Order creation time, used for reporting and fulfilment queues.
    placed_at = db.Column(db.DateTime, default=datetime.utcnow)

    # lazy='dynamic' because the items list is filtered/paginated (e.g. admin views).
    items = db.relationship('OrderItem', backref='order', lazy='dynamic')
    # The chosen delivery address; backref exposes address.orders for order history.
    shipping_address = db.relationship('Address', backref='orders')
