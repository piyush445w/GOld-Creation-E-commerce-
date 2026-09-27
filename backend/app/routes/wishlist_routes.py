# ---- Blueprint: wishlist ----
# Defines the 'wishlist' blueprint (URL prefix '/wishlist').
# Role: Handles customer wishlist functionality for both logged-in users and guests.
# Allows adding/removing products, viewing the wishlist page, and merging guest
# wishlist items into a user account upon login. Renders 'storefront/wishlist.html'.

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import current_user
from app import db
from app.models.wishlist import WishlistItem
from app.models.product import Product
from app.utils.currency_utils import get_visitor_currency, format_currency

wishlist_bp = Blueprint('wishlist', __name__)


# ---- Helpers ----
def _format(amount):
    """Format amount using the visitor's preferred currency from request context."""
    return format_currency(amount, get_visitor_currency(request))


class _GuestWishlistItem:
    """Wraps a Product so guest wishlist entries expose the same
    `.product` attribute the template uses for logged-in users' WishlistItems."""
    def __init__(self, product):
        self.product = product


def _is_ajax():
    """Detect AJAX requests via X-Requested-With header or JSON content type."""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json


def _get_guest_wishlist():
    """Retrieve or initialise the guest wishlist list stored in the session."""
    if 'guest_wishlist' not in session:
        session['guest_wishlist'] = []
    return session['guest_wishlist']


def _merge_guest_wishlist(user):
    """Merge guest session wishlist into the authenticated user's persistent wishlist.
    Pops guest product IDs from session, creates WishlistItem rows for any not
    already present, and commits the changes."""
    guest_product_ids = session.pop('guest_wishlist', [])
    if not guest_product_ids:
        return
    for product_id in guest_product_ids:
        existing = WishlistItem.query.filter_by(user_id=user.id, product_id=product_id).first()
        if not existing:
            item = WishlistItem(user_id=user.id, product_id=product_id)
            db.session.add(item)
    db.session.commit()


@wishlist_bp.route('/wishlist')
def view_wishlist():
    if current_user.is_authenticated:
        items = WishlistItem.query.filter_by(user_id=current_user.id).order_by(WishlistItem.added_at.desc()).all()
        return render_template('storefront/wishlist.html', items=items, format_currency=_format)
    guest_product_ids = _get_guest_wishlist()
    products = Product.query.filter(Product.id.in_(guest_product_ids), Product.is_active).all() if guest_product_ids else []
    items = [_GuestWishlistItem(p) for p in products]
    return render_template('storefront/wishlist.html', items=items, guest=True, format_currency=_format)


@wishlist_bp.route('/wishlist/toggle', methods=['POST'])
def toggle_wishlist():
    data = request.get_json(silent=True) or request.form
    product_id = data.get('product_id')
    if not product_id:
        if _is_ajax():
            return jsonify({'success': False, 'message': 'Product ID is required.'}), 400
        flash('Product ID is required.', 'error')
        return redirect(request.referrer or url_for('storefront.index'))

    if current_user.is_authenticated:
        existing = WishlistItem.query.filter_by(user_id=current_user.id, product_id=product_id).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
            if _is_ajax():
                return jsonify({'success': True, 'in_wishlist': False, 'message': 'Removed from wishlist.'})
            flash('Removed from wishlist.', 'success')
            return redirect(request.referrer or url_for('storefront.index'))
        else:
            item = WishlistItem(user_id=current_user.id, product_id=product_id)
            db.session.add(item)
            db.session.commit()
            if _is_ajax():
                return jsonify({'success': True, 'in_wishlist': True, 'message': 'Added to wishlist.'})
            flash('Added to wishlist.', 'success')
            return redirect(request.referrer or url_for('storefront.index'))
    else:
        guest_wishlist = _get_guest_wishlist()
        if product_id in guest_wishlist:
            guest_wishlist.remove(product_id)
            session['guest_wishlist'] = guest_wishlist
            if _is_ajax():
                return jsonify({'success': True, 'in_wishlist': False, 'message': 'Removed from wishlist.'})
            flash('Removed from wishlist.', 'success')
            return redirect(request.referrer or url_for('storefront.index'))
        else:
            guest_wishlist.append(product_id)
            session['guest_wishlist'] = guest_wishlist
            if _is_ajax():
                return jsonify({'success': True, 'in_wishlist': True, 'message': 'Added to wishlist.'})
            flash('Added to wishlist.', 'success')
            return redirect(request.referrer or url_for('storefront.index'))
