"""Tests for currency utilities: formatting, conversion, and visitor currency detection.

Covers the Indian ethnic wear store's multi-currency support (INR base, USD display).
"""
from app.utils.currency_utils import convert_amount, format_currency, get_visitor_currency
from app.models.currency import Currency


# Test class: verifies format_currency() produces correct locale-aware strings.
# Ensures price display is correct for INR (symbol prefix) and USD ($ prefix).
class TestFormatCurrency:
    # Verifies INR formatting uses 'INR' symbol with two decimal places.
    # Matters because all product prices are stored in INR and shown to Indian customers.
    def test_inr(self):
        assert format_currency(100, 'INR') == 'INR100.00'

    # Verifies USD formatting uses '$' symbol with two decimal places.
    # Matters for international visitors who see prices converted to USD.
    def test_usd(self):
        assert format_currency(100, 'USD') == '$100.00'


# Test class: verifies convert_amount() handles same-currency and cross-currency conversion.
# Uses Currency model exchange rates (INR=1.0 base, USD=83.0) to convert prices.
class TestConvertAmount:
    # Same-currency conversion should return the amount unchanged as float.
    # Ensures no rounding errors when source and target currency are identical.
    def test_same_currency(self):
        assert convert_amount(100, 'INR', 'INR') == 100.0

    # Cross-currency: 83 INR -> 1 USD at rate 83.0.
    # Seeds Currency table via db_session fixture, then verifies conversion math.
    # Critical for showing accurate USD prices to overseas buyers.
    def test_different_currency(self, db_session):
        inr = Currency(code='INR', symbol='INR', exchange_rate_to_inr=1.0)
        usd = Currency(code='USD', symbol='$', exchange_rate_to_inr=83.0)
        db_session.add_all([inr, usd])
        db_session.commit()

        assert convert_amount(83, 'INR', 'USD') == 1.0


# Test class: verifies get_visitor_currency() reads currency from cookie or defaults to INR.
# Determines which currency prices are displayed in for the current visitor.
class TestGetVisitorCurrency:
    # Cookie 'currency=USD' should be honored for returning visitors.
    # Simulates a request context with the cookie header set.
    def test_from_cookie(self, app):
        with app.test_request_context(headers={'Cookie': 'currency=USD'}):
            from flask import request
            assert get_visitor_currency(request) == 'USD'

    # No cookie -> defaults to INR (store's base currency).
    # Ensures new visitors see prices in INR without explicit preference.
    def test_default_inr(self, app):
        with app.test_request_context():
            from flask import request
            assert get_visitor_currency(request) == 'INR'
