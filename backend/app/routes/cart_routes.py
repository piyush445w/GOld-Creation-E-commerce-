from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.product_variant import ProductVariant
from app.models.cart import CartItem
from app.utils.currency_utils import convert_amount, format_currency
import uuid
from decimal import Decimal

# =============================================================================
# Blueprint: cart
# URL Prefix: (none - registered at root: /cart, /cart/add, /cart/update/<id>,
#   /cart/remove/<id>, /cart/merge, /cart/count, /currency/set)
# Role: Shopping-cart module. Supports both authenticated customers (cart rows
#   keyed by user_id) and anonymous guests (cart rows keyed by a UUID stored
#   in the session). Provides add/update/remove/merge/count and a currency
#   selector cookie, and dual-renders AJAX JSON or form-based flash redirects.
# Templates rendered: storefront/cart.html
# =============================================================================

cart_bp = Blueprint('cart', __name__)


# ---- Section: Session & Cart Helpers ----
# guest_session_id lazily creates and persists a UUID in the session so guest
# cart rows have a stable identity across requests (and across browser
# restarts when the session is permanent).
def guest_session_id():
    gid = session.get('guest_session_id')
    if not gid:
        gid = str(uuid.uuid4())
        session['guest_session_id'] = gid
        session.permanent = True
    return gid


# _get_cart_items returns the current visitor's cart rows: user-scoped when
# authenticated, guest-session-scoped otherwise.
def _get_cart_items():
    if current_user.is_authenticated:
        return CartItem.query.filter_by(user_id=current_user.id).all()
    gid = session.get('guest_session_id')
    if not gid:
        return []
    return CartItem.query.filter_by(guest_session_id=gid).all()


# _cart_subtotal sums price * quantity per item, preferring a variant's
# price_override when set, else the product's base_price. Decimal math avoids
# float rounding on currency totals.

def _cart_subtotal(items):
    total = Decimal('0')
    for item in items:
        if not item.variant:
            continue
        price = item.variant.price_override if item.variant.price_override else item.variant.product.base_price
        total += Decimal(str(price)) * Decimal(str(item.quantity))
    return float(total)


# _get_currency prefers the logged-in user's preferred_currency, else INR.
def _get_currency():
    currency = 'INR'
    if current_user.is_authenticated and current_user.preferred_currency:
        currency = current_user.preferred_currency
    return currency


def _format(amount):
    return format_currency(amount, _get_currency())


# _is_ajax detects AJAX/XHR requests so the route can return JSON instead of
# a flash + redirect (used by the cart UI widgets).
def _is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json


@cart_bp.route('/cart')
def view_cart():
    items = _get_cart_items()
    subtotal = _cart_subtotal(items)
    currency = 'INR'
    if current_user.is_authenticated and current_user.preferred_currency:
        currency = current_user.preferred_currency
    converted_subtotal = convert_amount(subtotal, 'INR', currency)
    return render_template(
        'storefront/cart.html',
        items=items,
        subtotal=subtotal,
        converted_subtotal=converted_subtotal,
        currency=currency,
        format_currency=_format
    )


@cart_bp.route('/cart/add', methods=['POST'])
def add_to_cart():
    data = request.get_json(silent=True) or request.form
    variant_id = data.get('product_variant_id')
    quantity = int(data.get('quantity', 1))

    if not variant_id:
        if _is_ajax():
            return jsonify({'success': False, 'message': 'Variant ID is required.'}), 400
        flash('Variant ID is required.', 'danger')
        return redirect(request.referrer or url_for('storefront.index'))

    variant = ProductVariant.query.get(variant_id)
    if not variant:
        if _is_ajax():
            return jsonify({'success': False, 'message': 'Product variant not found.'}), 404
        flash('Product variant not found.', 'danger')
        return redirect(request.referrer or url_for('storefront.index'))

    if variant.stock_quantity < quantity:
        if _is_ajax():
            return jsonify({'success': False, 'message': 'Insufficient stock.'}), 400
        flash('Insufficient stock.', 'danger')
        return redirect(request.referrer or url_for('storefront.index'))

    if current_user.is_authenticated:
        item = CartItem.query.filter_by(user_id=current_user.id, product_variant_id=variant_id).first()
    else:
        item = CartItem.query.filter_by(guest_session_id=guest_session_id(), product_variant_id=variant_id).first()

    if item:
        item.quantity += quantity
        if item.quantity > variant.stock_quantity:
            item.quantity = variant.stock_quantity
            flash('Quantity adjusted to available stock.', 'warning')
    else:
        item = CartItem(
            user_id=current_user.id if current_user.is_authenticated else None,
            guest_session_id=guest_session_id() if not current_user.is_authenticated else None,
            product_variant_id=variant_id,
            quantity=quantity
        )
        db.session.add(item)

    db.session.commit()

    if current_user.is_authenticated:
        count = CartItem.query.filter_by(user_id=current_user.id).count()
    else:
        count = CartItem.query.filter_by(guest_session_id=guest_session_id()).count()

    if _is_ajax():
        return jsonify({'success': True, 'cart_count': count, 'message': 'Added to cart.'})
    flash('Added to cart.', 'success')
    return redirect(request.referrer or url_for('storefront.index'))


@cart_bp.route('/cart/update/<int:item_id>', methods=['POST'])
def update_cart(item_id):
    item = CartItem.query.get_or_404(item_id)
    if current_user.is_authenticated:
        if item.user_id != current_user.id:
            if _is_ajax():
                return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
            flash('Unauthorized.', 'danger')
            return redirect(url_for('storefront.index'))
    else:
        if item.guest_session_id != guest_session_id():
            if _is_ajax():
                return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
            flash('Unauthorized.', 'danger')
            return redirect(url_for('storefront.index'))

    quantity = int(request.form.get('quantity', 1))
    if quantity < 1:
        if _is_ajax():
            return jsonify({'success': False, 'message': 'Quantity must be at least 1.'}), 400
        flash('Quantity must be at least 1.', 'danger')
        return redirect(request.referrer or url_for('storefront.index'))

    if quantity > item.variant.stock_quantity:
        if _is_ajax():
            return jsonify({'success': False, 'message': 'Insufficient stock.'}), 400
        flash('Insufficient stock.', 'danger')
        return redirect(request.referrer or url_for('storefront.index'))

    item.quantity = quantity
    db.session.commit()
    if _is_ajax():
        return jsonify({'success': True, 'message': 'Cart updated.'})
    flash('Cart updated.', 'success')
    return redirect(request.referrer or url_for('storefront.index'))


@cart_bp.route('/cart/remove/<int:item_id>', methods=['POST'])
def remove_from_cart(item_id):
    item = CartItem.query.get_or_404(item_id)
    if current_user.is_authenticated:
        if item.user_id != current_user.id:
            if _is_ajax():
                return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
            flash('Unauthorized.', 'danger')
            return redirect(url_for('storefront.index'))
    else:
        if item.guest_session_id != guest_session_id():
            if _is_ajax():
                return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
            flash('Unauthorized.', 'danger')
            return redirect(url_for('storefront.index'))

    db.session.delete(item)
    db.session.commit()
    if _is_ajax():
        return jsonify({'success': True, 'message': 'Item removed from cart.'})
    flash('Item removed from cart.', 'success')
    return redirect(request.referrer or url_for('storefront.index'))


@cart_bp.route('/cart/merge', methods=['POST'])
@login_required
def merge_cart():
    guest_items = CartItem.query.filter_by(guest_session_id=guest_session_id()).all()
    for guest_item in guest_items:
        existing = CartItem.query.filter_by(user_id=current_user.id, product_variant_id=guest_item.product_variant_id).first()
        if existing:
            existing.quantity += guest_item.quantity
            if existing.quantity > existing.variant.stock_quantity:
                existing.quantity = existing.variant.stock_quantity
            db.session.delete(guest_item)
        else:
            guest_item.user_id = current_user.id
            guest_item.guest_session_id = None
    db.session.commit()
    if _is_ajax():
        return jsonify({'success': True, 'message': 'Cart merged successfully.'})
    flash('Cart merged successfully.', 'success')
    return redirect(request.referrer or url_for('storefront.index'))


@cart_bp.route('/cart/count')
def cart_count():
    if current_user.is_authenticated:
        count = CartItem.query.filter_by(user_id=current_user.id).count()
    else:
        gid = session.get('guest_session_id')
        count = CartItem.query.filter_by(guest_session_id=gid).count() if gid else 0
    return jsonify({'count': count})


@cart_bp.route('/currency/set', methods=['POST'])
def set_currency():
    data = request.get_json(silent=True) or request.form
    currency = data.get('currency', 'INR').upper()
    response = jsonify({'success': True})
    response.set_cookie('currency', currency, max_age=60 * 60 * 24 * 365)
    return response
