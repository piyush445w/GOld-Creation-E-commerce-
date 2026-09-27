# -*- coding: utf-8 -*-
"""Display/settlement currencies for the storefront.

Every currency carries a rate to INR, the merchant's settlement currency. Order
snapshots that rate (Order.exchange_rate_used) so a price shown to a customer
can be audited against what was actually charged, even after rates change.
"""

from app import db
from sqlalchemy import Numeric
from datetime import datetime


# A currency offered for display and (optionally) for settlement.
class Currency(db.Model):
    __tablename__ = 'currencies'

    id = db.Column(db.Integer, primary_key=True)
    # ISO 4217 code, e.g. "INR", "USD"; matched against User.preferred_currency.
    code = db.Column(db.String(3), nullable=False)
    # Rendered symbol for price display, e.g. "₹" or "$".
    symbol = db.Column(db.String(10), nullable=False)
    # Rate to convert this currency into INR; high precision (6 dp) for FX maths.
    exchange_rate_to_inr = db.Column(Numeric(10, 6), default=1)
    # Whether orders may be charged in this currency vs. only displayed in it.
    is_settlement_enabled = db.Column(db.Boolean, default=False)
    # Stamped on insert and refreshed on every write, so the UI can warn on stale rates.
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
