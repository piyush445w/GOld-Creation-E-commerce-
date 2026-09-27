# =============================================================================
# currency_utils.py - Currency helpers for the Gold Creation storefront
# -----------------------------------------------------------------------------
# Centralises every currency concern: reading the visitor's preferred currency
# from the session cookie, converting amounts between INR and the visitor
# currency using rates cached in the currencies table, formatting amounts for
# display, and refreshing those cached rates from admin site settings.
# Rates are normalised to INR so any pair can be derived by division.
# =============================================================================
from datetime import datetime
from flask import current_app, request
from app import db
from app.models.currency import Currency


# Lookup symbols for the currencies we actually render; anything else falls back
# to printing the ISO code followed by a space.
CURRENCY_SYMBOLS = {
    'INR': 'INR',
    'USD': '$',
}


# Compute the from->to rate by dividing each currency's INR-normalised rate,
# falling back to 1.0 when either row is missing or degenerate.
def get_exchange_rate(from_currency, to_currency):
    if from_currency == to_currency:
        return 1.0

    from_curr = Currency.query.filter_by(code=from_currency).first()
    to_curr = Currency.query.filter_by(code=to_currency).first()

    if not from_curr or not to_curr:
        return 1.0

    from_rate = float(from_curr.exchange_rate_to_inr)
    to_rate = float(to_curr.exchange_rate_to_inr)

    if from_rate <= 0 or to_rate <= 0:
        return 1.0

    return from_rate / to_rate


# Convert a numeric amount from one currency to another using the cached rate.
def convert_amount(amount, from_currency, to_currency):
    rate = get_exchange_rate(from_currency, to_currency)
    return float(amount) * rate


# Read the visitor's display currency from the currency cookie, defaulting to
# INR; used by checkout to decide what to charge and how to render prices.
def get_visitor_currency(request):
    currency = request.cookies.get('currency')
    if currency:
        return 'USD' if currency.upper() == 'USD' else 'INR'
    return 'INR'


# Background job: refresh USD->INR from the admin-configured manual rate and
# upsert the rates into the currencies table. Returns True on success, False
# on any DB failure so the scheduler can log it without aborting the job.
def refresh_currency_rates():
    with current_app.app_context():
        from app.models.site_setting import SiteSetting

        manual_rate_setting = SiteSetting.query.filter_by(setting_key='currency_manual_rate').first()

        if manual_rate_setting and manual_rate_setting.setting_value:
            try:
                manual_rate = float(manual_rate_setting.setting_value)
            except (TypeError, ValueError):
                return True
        else:
            return True

        try:
            for code in ['INR', 'USD']:
                rate = 1.0 if code == 'INR' else manual_rate
                currency = Currency.query.filter_by(code=code).first()
                if currency:
                    currency.exchange_rate_to_inr = float(rate)
                    currency.last_updated = datetime.utcnow()
                else:
                    currency = Currency(
                        code=code,
                        symbol=CURRENCY_SYMBOLS[code],
                        exchange_rate_to_inr=float(rate),
                        is_settlement_enabled=True,
                    )
                    db.session.add(currency)
            db.session.commit()
        except Exception:
            db.session.rollback()
            return False

        return True


# Render a number with the currency's symbol/code and 2-decimal thousands separators.
def format_currency(amount, currency_code):
    code = currency_code.upper() if currency_code else 'INR'
    symbol = CURRENCY_SYMBOLS.get(code, code + ' ')
    return f'{symbol}{float(amount):,.2f}'
