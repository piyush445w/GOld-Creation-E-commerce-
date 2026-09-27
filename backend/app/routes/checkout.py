# -*- coding: utf-8 -*-
# =============================================================================
# checkout.py — Purchase/order lifecycle for Gold Creation
# -----------------------------------------------------------------------------
# This module owns the entire customer checkout journey: rendering the checkout
# page, "buy now" one-click purchases, coupon application, order placement,
# address handling (both saved and guest-entered), stock validation, and the
# Razorpay + PayPal payment flows (initiate + verify). It is the single place
# where a cart/session is converted into a persisted Order row.
# =============================================================================
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import current_user
from app import db
from app.models.cart import CartItem
from app.models.address import Address
from app.models.coupon import Coupon
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product_variant import ProductVariant
from app.models.currency import Currency
from app.models.user import User
from app.utils.currency_utils import get_visitor_currency, convert_amount, format_currency
from werkzeug.security import generate_password_hash
from datetime import datetime
import uuid
import os
import hmac
import hashlib
import logging
import requests

logger = logging.getLogger(__name__)

checkout_bp = Blueprint('checkout', __name__)


# ---------------------------------------------------------------------------
# Internal helpers — currency display, cart aggregation, guest user, buy-now
# ---------------------------------------------------------------------------

# Resolve the currency to display/charge for the current request (cookie or INR).

def _get_currency():
    return get_visitor_currency(request)

# Format a numeric amount using the visitor's currency (for template rendering).


def _format(amount):
    return format_currency(amount, _get_currency())

# Aggregate the active cart (logged-in user_id OR guest session id) into a list
# of line items and a subtotal in raw INR base units. Returns ([items], total).


def _cart_total_and_items():
    if current_user.is_authenticated:
        items = CartItem.query.filter_by(user_id=current_user.id).all()
    else:
        gid = session.get('guest_session_id')
        if not gid:
            return [], 0
        items = CartItem.query.filter_by(guest_session_id=gid).all()
    total = 0
    for item in items:
        # Use the variant's override price when set, else the product base price.
        price = item.variant.price_override if item.variant and item.variant.price_override else item.variant.product.base_price
        total += float(price) * item.quantity
    return items, total

# For guest checkouts, lazily create a shadow "customer" User row so the order
# has a user_id to attach to; the guest session is preserved in the session cookie.


def _get_or_create_guest_user():
    guest_user_id = session.get('guest_user_id')
    if guest_user_id:
        user = User.query.get(guest_user_id)
        if user and user.role == 'customer':
            return user
    email = 'guest_' + uuid.uuid4().hex[:8] + '@guest.local'
    currency = request.form.get('currency', 'INR')
    user = User(
        name='Guest',
        email=email,
        password_hash=generate_password_hash(str(uuid.uuid4())),
        phone=request.form.get('phone', ''),
        country=request.form.get('country', 'IN'),
        preferred_currency=currency,
        role='customer'
    )
    db.session.add(user)
    db.session.flush()
    session['guest_user_id'] = user.id
    return user

# Build a one-item "list" from the session's buy-now payload, with stock + qty
# validation; used by both the checkout page and order placement.


def _get_buy_now_items():
    data = session.get('buy_now')
    if not data:
        return [], 0
    variant = ProductVariant.query.get(data.get('variant_id'))
    if not variant:
        session.pop('buy_now', None)
        return [], 0
    quantity = int(data.get('quantity', 1))
    if quantity < 1 or variant.stock_quantity < quantity:
        session.pop('buy_now', None)
        return [], 0
    price = variant.price_override if variant and variant.price_override else variant.product.base_price
    total = float(price) * quantity

    class _BNItem:
        pass
    item = _BNItem()
    item.variant = variant
    item.quantity = quantity
    item.product = variant.product
    return [item], total


# ---------------------------------------------------------------------------
# Routes — checkout page rendering
# ---------------------------------------------------------------------------

# Render the checkout page for either the logged-in/guest cart or a buy-now
# item. Computes the INR subtotal, converts it to the visitor currency, applies
# any coupon from the query string, and passes totals + PayPal client id +
# exchange rate to the template.
@checkout_bp.route('/checkout', methods=['GET'])
def checkout():
    if not current_user.is_authenticated:
        flash('Please log in to place your order.', 'warning')
        return redirect(url_for('auth.login', next=request.full_path))

    buy_now_mode = bool(session.get('buy_now'))
    if buy_now_mode:
        items, subtotal = _get_buy_now_items()
    else:
        items, subtotal = _cart_total_and_items()
    if not items:
        session.pop('buy_now', None)
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('cart.view_cart'))

    currency = _get_currency()
    converted_subtotal = convert_amount(subtotal, 'INR', currency)

    addresses = []
    if current_user.is_authenticated:
        addresses = Address.query.filter_by(user_id=current_user.id).all()

    coupon_code = request.args.get('coupon', '')
    discount = 0
    coupon_obj = None
    if coupon_code:
        # --- Coupon validation: active, within date range, under usage limit, meets min order value ---
        coupon_obj = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
        if coupon_obj and coupon_obj.valid_from <= datetime.utcnow() <= coupon_obj.valid_to:
            if coupon_obj.usage_limit is None or coupon_obj.times_used < coupon_obj.usage_limit:
                if converted_subtotal >= float(coupon_obj.min_order_value):
                    # --- Discount computation: percent type vs fixed amount, capped at the subtotal ---
                    if coupon_obj.discount_type == 'percent':
                        discount = converted_subtotal * float(coupon_obj.discount_value) / 100
                    else:
                        discount = float(coupon_obj.discount_value)
                    if discount > converted_subtotal:
                        discount = converted_subtotal

    shipping = 0
    total = converted_subtotal - discount + shipping

    # --- Exchange rate: derived from stored INR-normalised rates for display vs charge currency ---
    from_curr = Currency.query.filter_by(code='INR').first()
    to_curr = Currency.query.filter_by(code=currency).first()
    exchange_rate = 1.0
    if from_curr and to_curr:
        exchange_rate = float(from_curr.exchange_rate_to_inr) / float(to_curr.exchange_rate_to_inr)

    return render_template(
        'storefront/checkout.html',
        items=items,
        subtotal=converted_subtotal,
        discount=discount,
        shipping=shipping,
        total=total,
        currency=currency,
        addresses=addresses,
        coupon=coupon_obj,
        format_currency=_format,
        paypal_client_id=os.environ.get('PAYPAL_CLIENT_ID', ''),
        exchange_rate=exchange_rate,
        is_buy_now=buy_now_mode
    )


# ---------------------------------------------------------------------------
# Routes — buy now (one-click purchase from product page)
# ---------------------------------------------------------------------------

# Stash a single variant+quantity in the session and redirect to checkout;
# validates variant existence, minimum quantity and available stock first.
# Requires authentication since buy-now leads directly to checkout.
@checkout_bp.route('/checkout/buy-now', methods=['POST'])
def buy_now():
    if not current_user.is_authenticated:
        flash('Please log in to use Buy Now.', 'warning')
        return redirect(url_for('auth.login', next=request.referrer or url_for('storefront.index')))

    variant_id = request.form.get('product_variant_id')
    quantity = request.form.get('quantity', 1, type=int)

    if not variant_id:
        flash('Please select a variant.', 'warning')
        return redirect(request.referrer or url_for('storefront.index'))

    variant = ProductVariant.query.get(variant_id)
    if not variant:
        flash('Product variant not found.', 'danger')
        return redirect(request.referrer or url_for('storefront.index'))

    if quantity < 1:
        flash('Quantity must be at least 1.', 'warning')
        return redirect(request.referrer or url_for('storefront.index'))

    if variant.stock_quantity < quantity:
        flash('Insufficient stock available.', 'danger')
        return redirect(request.referrer or url_for('storefront.index'))

    session['buy_now'] = {
        'variant_id': str(variant_id),
        'quantity': quantity
    }
    session.permanent = True
    return redirect(url_for('checkout.checkout', buy_now=1))


# ---------------------------------------------------------------------------
# Routes — coupon application (AJAX)
# ---------------------------------------------------------------------------

# Validate a coupon code against the cart total and return the discount and
# new total as JSON for live preview on the checkout page. Checks active
# status, validity window, usage limit and minimum order value.
# Requires authentication since coupons are applied at checkout.
@checkout_bp.route('/checkout/apply-coupon', methods=['POST'])
def apply_coupon():
    if not current_user.is_authenticated:
        return jsonify({
            'success': False,
            'error': 'login_required',
            'login_url': url_for('auth.login', next=url_for('checkout.checkout')),
            'message': 'Please log in to apply coupons.'
        }), 401

    data = request.get_json(silent=True) or request.form
    coupon_code = data.get('coupon_code', '').strip().upper()
    cart_total = float(data.get('cart_total', 0))

    coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
    if not coupon:
        return jsonify({'success': False, 'message': 'Invalid coupon code.'}), 404

    now = datetime.utcnow()
    if coupon.valid_from > now:
        return jsonify({'success': False, 'message': 'Coupon is not yet valid.'}), 400
    if coupon.valid_to < now:
        return jsonify({'success': False, 'message': 'Coupon has expired.'}), 400
    if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
        return jsonify({'success': False, 'message': 'Coupon usage limit reached.'}), 400
    if cart_total < float(coupon.min_order_value):
        return jsonify({'success': False, 'message': 'Minimum order value not met.'}), 400

    if coupon.discount_type == 'percent':
        discount = cart_total * float(coupon.discount_value) / 100
    else:
        discount = float(coupon.discount_value)

    if discount > cart_total:
        discount = cart_total

    new_total = cart_total - discount
    return jsonify({
        'success': True,
        'discount': round(discount, 2),
        'new_total': round(new_total, 2),
        'message': 'Coupon applied successfully.'
    })


# ---------------------------------------------------------------------------
# Routes — order placement (the core transaction)
# ---------------------------------------------------------------------------

# Convert the cart or buy-now payload into a real Order + OrderItem rows in a
# single DB transaction. Validates stock, applies the coupon, decrements
# variant stock, clears the cart (unless buy-now), commits, then fires the
# order-confirmation email and SMS notification.
@checkout_bp.route('/checkout/place-order', methods=['POST'])
def place_order():
    if not current_user.is_authenticated:
        login_url = url_for('auth.login', next=request.full_path)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
        if is_ajax:
            return jsonify({
                'success': False,
                'error': 'login_required',
                'login_url': login_url,
                'message': 'Please log in to place your order.'
            }), 401
        flash('Please log in to place your order.', 'warning')
        return redirect(login_url)

    buy_now_data = session.get('buy_now')
    is_buy_now = bool(buy_now_data)
    if is_buy_now:
        items, subtotal = _get_buy_now_items()
    else:
        items, subtotal = _cart_total_and_items()
    if not items:
        session.pop('buy_now', None)
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('cart.view_cart'))

    out_of_stock = [item for item in items if item.variant.stock_quantity < item.quantity]
    if out_of_stock:
        names = ', '.join(item.variant.product.name for item in out_of_stock)
        flash(f'Sorry, some items no longer have enough stock and were not ordered: {names}. Please update your cart.', 'danger')
        return redirect(url_for('cart.view_cart'))

    currency = _get_currency()
    converted_subtotal = convert_amount(subtotal, 'INR', currency)

    coupon_code = request.form.get('coupon_code', '').strip().upper()
    discount = 0
    coupon_obj = None
    if coupon_code:
        # --- Coupon validation: active, within date range, under usage limit, meets min order value ---
        coupon_obj = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
        if coupon_obj and coupon_obj.valid_from <= datetime.utcnow() <= coupon_obj.valid_to:
            if coupon_obj.usage_limit is None or coupon_obj.times_used < coupon_obj.usage_limit:
                if converted_subtotal >= float(coupon_obj.min_order_value):
                    # --- Discount computation: percent type vs fixed amount, capped at the subtotal ---
                    if coupon_obj.discount_type == 'percent':
                        discount = converted_subtotal * float(coupon_obj.discount_value) / 100
                    else:
                        discount = float(coupon_obj.discount_value)
                    if discount > converted_subtotal:
                        discount = converted_subtotal
                    coupon_obj.times_used += 1

    shipping = 0
    total = converted_subtotal - discount + shipping

    # --- Exchange rate: derived from stored INR-normalised rates for display vs charge currency ---
    from_curr = Currency.query.filter_by(code='INR').first()
    to_curr = Currency.query.filter_by(code=currency).first()
    if from_curr and to_curr:
        exchange_rate = float(from_curr.exchange_rate_to_inr) / float(to_curr.exchange_rate_to_inr)
    else:
        exchange_rate = 1.0

    # --- Resolve the placing user: authenticated customer ---
    user = current_user

    address_id = request.form.get('address_id')
    if address_id:
        # --- Reuse a saved address (ownership-checked for logged-in users) ---
        address = Address.query.filter_by(id=address_id, user_id=current_user.id).first()
        if not address:
            flash('Invalid address.', 'danger')
            return redirect(url_for('checkout.checkout'))
    else:
        # --- Persist a one-off shipping address entered inline on the checkout form ---
        address = Address(
            user_id=user.id,
            label='Shipping',
            line1=request.form.get('line1', ''),
            line2=request.form.get('line2', ''),
            city=request.form.get('city', ''),
            state=request.form.get('state', ''),
            country=request.form.get('country', ''),
            postal_code=request.form.get('postal_code', ''),
            is_default=False
        )
        db.session.add(address)
        db.session.flush()

    # --- Build the Order row; currency/amounts are stored in the visitor's currency ---
    order_number = uuid.uuid4().hex.upper()
    order = Order(
        user_id=user.id,
        order_number=order_number,
        status='pending',
        subtotal=converted_subtotal,
        discount_amount=discount,
        shipping_fee=shipping,
        total=total,
        display_currency=currency,
        charged_currency=currency,
        charged_amount=total,
        exchange_rate_used=exchange_rate,
        shipping_address_id=address.id,
        payment_method=request.form.get('payment_method', 'cod')
    )
    db.session.add(order)
    db.session.flush()

    # --- Create OrderItem snapshots and decrement variant stock within the transaction ---
    for item in items:
        price = item.variant.price_override if item.variant and item.variant.price_override else item.variant.product.base_price
        converted_price = convert_amount(price, 'INR', currency)
        order_item = OrderItem(
            order_id=order.id,
            product_variant_id=item.variant.id,
            product_name_snapshot=item.variant.product.name,
            unit_price_snapshot=converted_price,
            quantity=item.quantity,
            subtotal=converted_price * item.quantity
        )
        db.session.add(order_item)
        item.variant.stock_quantity -= item.quantity

    # --- Clear the cart for normal cart checkout; buy-now leaves the cart untouched ---
    if not is_buy_now:
        for item in items:
            db.session.delete(item)

    session.pop('buy_now', None)
    db.session.commit()

    # --- Fire order-confirmation notifications (email + SMS) after a successful commit ---
    from app.utils.email import send_order_confirmation
    from app.utils.sms import send_order_notification
    send_order_confirmation(order)
    if order.user and order.user.phone:
        send_order_notification(order, order.status)

    # --- For gateway payments, return JSON so the frontend can drive the payment flow ---
    if order.payment_method in ['razorpay', 'paypal']:
        return jsonify({'success': True, 'order_number': order_number, 'payment_method': order.payment_method})

    return redirect(url_for('checkout.order_confirmation', order_number=order_number))


# ---------------------------------------------------------------------------
# Routes — payment initiation (Razorpay / PayPal)
# ---------------------------------------------------------------------------

# Start a gateway payment for an already-placed order. For Razorpay it creates
# an external order via the REST API and stores the gateway order id; for PayPal
# it simply returns the order details for the client SDK. Enforces a single
# payment per order and fails gracefully when credentials are missing.
# Requires authentication since only authenticated users can place orders.
@checkout_bp.route('/checkout/initiate-payment', methods=['POST'])
def initiate_payment():
    if not current_user.is_authenticated:
        return jsonify({
            'success': False,
            'error': 'login_required',
            'login_url': url_for('auth.login', next=url_for('checkout.checkout')),
            'message': 'Please log in to initiate payment.'
        }), 401

    data = request.get_json(silent=True) or request.form
    payment_method = data.get('payment_method')
    order_id = data.get('order_id')

    order = Order.query.filter_by(order_number=order_id).first()
    if not order:
        return jsonify({'success': False, 'message': 'Order not found.'}), 404
    if order.payment_status == 'paid':
        return jsonify({'success': False, 'message': 'This order has already been paid.'}), 400

    if payment_method == 'razorpay':
        key_id = os.environ.get('RAZORPAY_KEY_ID', '')
        key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
        if not key_id or not key_secret:
            return jsonify({'success': False, 'message': 'Card/UPI payments are not configured yet. Please choose Cash on Delivery.'}), 503
        try:
            # --- External API call: create a Razorpay order keyed to our order_number ---
            resp = requests.post(
                'https://api.razorpay.com/v1/orders',
                auth=(key_id, key_secret),
                json={
                    'amount': int(round(float(order.charged_amount) * 100)),  # amount in smallest currency unit (paise)
                    'currency': order.charged_currency,
                    'receipt': order.order_number,
                },
                timeout=10
            )
            resp.raise_for_status()
            rp_order = resp.json()
        except Exception:
            # --- Error handling: never leak the raw upstream error to the client ---
            logger.exception('Failed to create Razorpay order for %s', order.order_number)
            return jsonify({'success': False, 'message': 'Could not start the payment. Please try again.'}), 502

        order.gateway_order_id = rp_order['id']
        db.session.commit()

        return jsonify({
            'success': True,
            'payment_method': 'razorpay',
            'order_id': rp_order['id'],
            'amount': rp_order['amount'],
            'currency': rp_order['currency'],
            'key_id': key_id
        })
    elif payment_method == 'paypal':
        client_id = os.environ.get('PAYPAL_CLIENT_ID', '')
        if not client_id:
            return jsonify({'success': False, 'message': 'PayPal is not configured yet. Please choose another payment method.'}), 503
        order.gateway_order_id = None
        db.session.commit()
        return jsonify({
            'success': True,
            'payment_method': 'paypal',
            'order_id': order.order_number,
            'amount': float(order.charged_amount),
            'currency': order.charged_currency
        })
    else:
        return jsonify({'success': False, 'message': 'Unsupported payment method.'}), 400


# --- Verify a Razorpay payment signature using HMAC-SHA256 over "<order_id>|<payment_id>" ---

def _verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
    if not key_secret:
        return False
    payload = f'{razorpay_order_id}|{razorpay_payment_id}'.encode('utf-8')
    expected = hmac.new(key_secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, razorpay_signature or '')


# --- Verify a PayPal capture by fetching the order via the REST API and comparing amount+currency ---

def _verify_paypal_capture(order):
    client_id = os.environ.get('PAYPAL_CLIENT_ID', '')
    client_secret = os.environ.get('PAYPAL_CLIENT_SECRET', '')
    base_url = 'https://api-m.sandbox.paypal.com' if os.environ.get('PAYPAL_MODE', 'sandbox') != 'live' else 'https://api-m.paypal.com'
    if not client_id or not client_secret:
        return False
    try:
        # --- External API call: OAuth2 client-credentials token for the PayPal REST API ---
        token_resp = requests.post(
            f'{base_url}/v1/oauth2/token',
            auth=(client_id, client_secret),
            data={'grant_type': 'client_credentials'},
            timeout=10
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()['access_token']

        # --- External API call: fetch the PayPal order to confirm COMPLETED status and amount ---
        order_resp = requests.get(
            f'{base_url}/v2/checkout/orders/{order.gateway_order_id}',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        order_resp.raise_for_status()
        paypal_order = order_resp.json()
        if paypal_order.get('status') != 'COMPLETED':
            return False
        paid_amount = float(paypal_order['purchase_units'][0]['amount']['value'])
        paid_currency = paypal_order['purchase_units'][0]['amount']['currency_code']
        # --- Reconcile the captured amount/currency against the stored order totals ---
        return abs(paid_amount - float(order.charged_amount)) < 0.01 and paid_currency == order.charged_currency
    except Exception:
        logger.exception('Failed to verify PayPal capture for order %s', order.order_number)
        return False


# ---------------------------------------------------------------------------
# Routes — payment callback / verification (Razorpay + PayPal)
# ---------------------------------------------------------------------------

# Finalise an order after the gateway returns. Verifies the Razorpay HMAC
# signature (or PayPal capture status/amount) and, only on success, flips the
# order to payment_status='paid' + status='processing' in a single commit.
# Requires authentication since only authenticated users can place orders.
@checkout_bp.route('/checkout/payment-callback', methods=['POST'])
def payment_callback():
    if not current_user.is_authenticated:
        return jsonify({
            'success': False,
            'error': 'login_required',
            'login_url': url_for('auth.login', next=url_for('checkout.checkout')),
            'message': 'Please log in to complete payment.'
        }), 401

    data = request.get_json(silent=True) or request.form
    order_number = data.get('order_number')

    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return jsonify({'success': False, 'message': 'Order not found.'}), 404
    if order.payment_status == 'paid':
        return jsonify({'success': True, 'message': 'Payment already confirmed.'})

    if order.payment_method == 'razorpay':
        razorpay_order_id = data.get('razorpay_order_id')
        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_signature = data.get('razorpay_signature')
        if (not razorpay_order_id or razorpay_order_id != order.gateway_order_id
                or not _verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature)):
            logger.warning('Razorpay signature verification failed for order %s', order.order_number)
            return jsonify({'success': False, 'message': 'Payment could not be verified.'}), 400
        order.payment_status = 'paid'
        order.status = 'processing'
        db.session.commit()
        return jsonify({'success': True, 'message': 'Payment verified.'})

    elif order.payment_method == 'paypal':
        paypal_order_id = data.get('paypal_order_id')
        if not paypal_order_id:
            return jsonify({'success': False, 'message': 'Missing PayPal order reference.'}), 400
        order.gateway_order_id = paypal_order_id
        if not _verify_paypal_capture(order):
            logger.warning('PayPal capture verification failed for order %s', order.order_number)
            return jsonify({'success': False, 'message': 'Payment could not be verified.'}), 400
        order.payment_status = 'paid'
        order.status = 'processing'
        db.session.commit()
        return jsonify({'success': True, 'message': 'Payment verified.'})

    return jsonify({'success': False, 'message': 'Unsupported payment method for verification.'}), 400


# ---------------------------------------------------------------------------
# Routes — order confirmation page (post-purchase thank-you)
# ---------------------------------------------------------------------------

# Render the post-purchase confirmation page for a placed order, formatting all
# amounts in the order's stored display currency.
@checkout_bp.route('/checkout/confirmation/<order_number>')
def order_confirmation(order_number):
    order = Order.query.filter_by(order_number=order_number, user_id=current_user.id).first_or_404()
    return render_template(
        'storefront/order_confirmation.html',
        order=order,
        format_currency=lambda amount: format_currency(amount, order.display_currency)
    )
