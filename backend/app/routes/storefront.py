from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from sqlalchemy import or_
from app import db
from app.models.product import Product
from app.models.category import Category
from app.models.banner import Banner
from app.models.site_setting import SiteSetting
from app.models.review import Review
from app.models.product_media import ProductMedia
from app.models.product_variant import ProductVariant
from app.models.wishlist import WishlistItem
from app.models.cart import CartItem
from app.models.page import Page
from app.models.order import Order
from app.models.newsletter import NewsletterSubscriber
from app.models.address import Address
from app.utils.currency_utils import get_visitor_currency, convert_amount, format_currency

# =============================================================================
# Blueprint: storefront
# URL Prefix: (none - registered at root, e.g. '/', '/shop', '/product/<slug>')
# Role: Public customer-facing catalog & account module. Powers the end of the
#   purchase funnel from discovery (home/shop/category/search) through product
#   detail, reviews, and cart/wishlist status, plus CMS pages and the
#   logged-in account area (orders, address book).
# Templates rendered:
#   storefront/home.html, storefront/category.html, storefront/product_detail.html,
#   storefront/search.html, storefront/page.html, storefront/account_orders.html,
#   storefront/account.html, storefront/account_addresses.html,
#   storefront/account_address_form.html
# =============================================================================

storefront_bp = Blueprint('storefront', __name__)


# ---- Section: Request Helpers ----
# Centralises visitor-currency resolution so every route can convert INR
# prices to the cookie-selected currency without duplicating logic.

def _get_currency():
    return get_visitor_currency(request)

def _convert(amount):
    currency = _get_currency()
    return convert_amount(amount, 'INR', currency)


def _format(amount):
    currency = _get_currency()
    return format_currency(amount, currency)


# Route: GET /  (public)
# Renders the landing page: active banners, 8 featured products, 6 active
# categories, and all site settings for the template's branding blocks.
@storefront_bp.route('/')
def index():
    banners = Banner.query.filter_by(is_active=True).order_by(Banner.display_order).all()
    featured_products = Product.query.filter_by(is_active=True).limit(8).all()
    categories = Category.query.filter_by(is_active=True).limit(6).all()
    # Build a settings dict keyed by setting_key so the template can look up
    # values (logo, site name, contact) without per-query calls.
    settings = {s.setting_key: s.setting_value for s in SiteSetting.query.all()}
    return render_template('storefront/home.html',
        banners=banners,
        featured_products=featured_products,
        categories=categories,
        settings=settings,
        format_currency=_format
    )


# Route: GET /shop  (public)
# Filterable/paginated product catalog. Accepts category_slug, festival tag,
# price range, free-text search (name/description/sku), and a sort param.
# Renders storefront/category.html with is_shop=True so the shared template
# can distinguish the shop layout from a category page.
@storefront_bp.route('/shop')
def shop():
    query = Product.query.filter_by(is_active=True)
    category_slug = request.args.get('category_slug')
    festival = request.args.get('festival')
    sort = request.args.get('sort', 'newest')
    q = request.args.get('q', '').strip()
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)

    # Resolve the requested category; if valid, scope the query to its id.
    # Unknown slugs simply leave the query unfiltered (no 404 for /shop).
    active_category = None
    if category_slug:
        active_category = Category.query.filter_by(slug=category_slug, is_active=True).first()
        if active_category:
            query = query.filter_by(category_id=active_category.id)

    # Festival filter keeps only products tagged for festival marketing.
    if festival == 'true':
        query = query.filter(Product.festival_tag.isnot(None))

    # Price-range filters bound the base_price column.
    if min_price is not None:
        query = query.filter(Product.base_price >= min_price)
    if max_price is not None:
        query = query.filter(Product.base_price <= max_price)

    # Free-text search uses LIKE across name, description and sku.
    if q:
        search = "%" + q + "%"
        query = query.filter(
            or_(
                Product.name.like(search),
                Product.description.like(search),
                Product.sku.like(search)
            )
        )

    # Sort: default is newest (created_at desc); alternatives are price asc/desc.
    if sort == 'price_low':
        query = query.order_by(Product.base_price.asc())
    elif sort == 'price_high':
        query = query.order_by(Product.base_price.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    # Paginate at 12 items per page; error_out=False avoids 404 on out-of-range pages.
    page = request.args.get('page', 1, type=int)
    per_page = 12
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    products = pagination.items
    categories = Category.query.filter_by(is_active=True).limit(6).all()

    return render_template('storefront/category.html',
        products=products,
        categories=categories,
        pagination=pagination,
        sort=sort,
        q=q,
        min_price=min_price,
        max_price=max_price,
        active_category=active_category,
        is_shop=True,
        format_currency=_format
    )


# ---- Section: Category Pages ----
# Route: GET /category/<slug>  (public)
# Dedicated category landing page. 404s when the slug is inactive or missing,
# which keeps SEO-friendly URLs honest. Reuses storefront/category.html.
@storefront_bp.route('/category/<slug>')
def category(slug):
    category = Category.query.filter_by(slug=slug, is_active=True).first_or_404()
    query = Product.query.filter_by(category_id=category.id, is_active=True)
    sort = request.args.get('sort', 'newest')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)

    # Price + sort filters mirror /shop but are scoped to this category's id.
    if min_price is not None:
        query = query.filter(Product.base_price >= min_price)
    if max_price is not None:
        query = query.filter(Product.base_price <= max_price)

    if sort == 'price_low':
        query = query.order_by(Product.base_price.asc())
    elif sort == 'price_high':
        query = query.order_by(Product.base_price.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    page = request.args.get('page', 1, type=int)
    per_page = 12
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    products = pagination.items
    categories = Category.query.filter_by(is_active=True).limit(6).all()
    return render_template('storefront/category.html',
        category=category,
        active_category=category,
        products=products,
        categories=categories,
        pagination=pagination,
        sort=sort,
        min_price=min_price,
        max_price=max_price,
        format_currency=_format
    )


# ---- Section: Product Detail & Related Content ----
# Route: GET /product/<slug>  (public)
# Single-product view. Loads media, variants, approved reviews, and related
# products (same category, excluding self, limited to 4). Also computes the
# per-variant "in_cart" flag so the template can show "Added to cart" states.
@storefront_bp.route('/product/<slug>')
def product_detail(slug):
    product = Product.query.filter_by(slug=slug, is_active=True).first_or_404()
    media = ProductMedia.query.filter_by(product_id=product.id, is_active=True).order_by(ProductMedia.display_order).all()
    variants = ProductVariant.query.filter_by(product_id=product.id).all()
    reviews = Review.query.filter_by(product_id=product.id, is_approved=True).order_by(Review.created_at.desc()).all()

    # Convert base price once for the template's display block.
    currency = _get_currency()
    converted_price = convert_amount(product.base_price, 'INR', currency)

    # Determine whether the current visitor has this product in wishlist/cart.
    # For guests we fall back to the session's guest_session_id.
    in_wishlist = False
    in_cart_variant_ids = set()
    if current_user.is_authenticated:
        in_wishlist = WishlistItem.query.filter_by(user_id=current_user.id, product_id=product.id).first() is not None
        cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
        in_cart_variant_ids = {item.product_variant_id for item in cart_items}
    else:
        guest_gid = session.get('guest_session_id')
        if guest_gid:
            cart_items = CartItem.query.filter_by(guest_session_id=guest_gid).all()
            in_cart_variant_ids = {item.product_variant_id for item in cart_items}

    # Serialize variants for the template, flagging which are already in the
    # visitor's cart so the UI can disable/label the add-to-cart button.
    variants = [
        {
            'id': variant.id,
            'size': variant.size,
            'color': variant.color,
            'stock_quantity': variant.stock_quantity,
            'in_cart': variant.id in in_cart_variant_ids,
            'price_override': float(variant.price_override) if variant.price_override is not None else None,
        }
        for variant in variants
    ]

    # Related products: same category, excluding the current product, active only.
    related_products = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != product.id,
        Product.is_active == True
    ).limit(4).all()

    return render_template('storefront/product_detail.html',
        product=product,
        media=media,
        variants=variants,
        reviews=reviews,
        related_products=related_products,
        in_wishlist=in_wishlist,
        converted_price=converted_price,
        format_currency=_format
    )

# ---- Section: Search & CMS Pages ----
# Route: GET /search  (public)
# Standalone search results page. Same LIKE logic as /shop but no category,
# festival, or price filters; pagination is 12/page.
@storefront_bp.route('/search')
def search():
    q = request.args.get('q', '').strip()
    query = Product.query.filter_by(is_active=True)
    if q:
        search = "%" + q + "%"
        query = query.filter(
            or_(
                Product.name.like(search),
                Product.description.like(search),
                Product.sku.like(search)
            )
        )
    page = request.args.get('page', 1, type=int)
    per_page = 12
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    products = pagination.items
    return render_template('storefront/search.html',
        products=products,
        pagination=pagination,
        q=q,
        format_currency=_format
    )


# Route: GET /page/<slug>  (public)
# Renders a static CMS page (About, Shipping, Returns, etc.) only if published.
@storefront_bp.route('/page/<slug>')
def page(slug):
    page = Page.query.filter_by(slug=slug, is_published=True).first_or_404()
    return render_template('storefront/page.html', page=page)


# ---- Section: Account Pages (login_required) ----
# Route: GET /account/orders  (login_required)
# Paginated order history for the logged-in customer, newest first.
@storefront_bp.route('/account/orders')
@login_required
def account_orders():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    pagination = Order.query.filter_by(user_id=current_user.id).order_by(Order.placed_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    orders = pagination.items
    return render_template('storefront/account_orders.html',
        orders=orders,
        pagination=pagination,
        format_currency=format_currency
    )


# Route: GET /account  (login_required)
# Account dashboard landing page.
@storefront_bp.route('/account')
@login_required
def account():
    return render_template('storefront/account.html')


# Route: GET /account/addresses  (login_required)
# Lists the logged-in customer's saved addresses for checkout selection.
@storefront_bp.route('/account/addresses')
@login_required
def account_addresses():
    addresses = Address.query.filter_by(user_id=current_user.id).all()
    return render_template('storefront/account_addresses.html', addresses=addresses)


# ---- Section: Address CRUD (login_required) ----
# Route: GET/POST /account/addresses/new  (login_required)
# Creates a new address. If the user marks it default OR it is their first
# address, the existing default is unset and this one becomes default.
@storefront_bp.route('/account/addresses/new', methods=['GET', 'POST'])
@login_required
def account_address_new():
    if request.method == 'POST':
        is_default = bool(request.form.get('is_default'))
        has_existing = Address.query.filter_by(user_id=current_user.id).first() is not None
        if is_default or not has_existing:
            Address.query.filter_by(user_id=current_user.id, is_default=True).update({'is_default': False})
            is_default = True
        address = Address(
            user_id=current_user.id,
            label=request.form.get('label', ''),
            line1=request.form.get('line1', ''),
            line2=request.form.get('line2', ''),
            city=request.form.get('city', ''),
            state=request.form.get('state', ''),
            country=request.form.get('country', ''),
            postal_code=request.form.get('postal_code', ''),
            is_default=is_default
        )
        db.session.add(address)
        db.session.commit()
        flash('Address added successfully.', 'success')
        return redirect(url_for('storefront.account_addresses'))
    return render_template('storefront/account_address_form.html')


# Route: GET/POST /account/addresses/<id>/edit  (login_required)
# Edits an existing address; scoping by user_id prevents IDOR. Setting default
# clears the default flag from all other addresses first.
@storefront_bp.route('/account/addresses/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def account_address_edit(id):
    address = Address.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        is_default = bool(request.form.get('is_default'))
        if is_default:
            Address.query.filter(Address.user_id == current_user.id, Address.id != address.id).update({'is_default': False})
        address.label = request.form.get('label', '')
        address.line1 = request.form.get('line1', '')
        address.line2 = request.form.get('line2', '')
        address.city = request.form.get('city', '')
        address.state = request.form.get('state', '')
        address.country = request.form.get('country', '')
        address.postal_code = request.form.get('postal_code', '')
        address.is_default = is_default
        db.session.commit()
        flash('Address updated successfully.', 'success')
        return redirect(url_for('storefront.account_addresses'))
    return render_template('storefront/account_address_form.html', address=address)


# Route: POST /account/addresses/<id>/delete  (login_required)
# Deletes an address, scoped to the logged-in user to prevent IDOR.
@storefront_bp.route('/account/addresses/<int:id>/delete', methods=['POST'])
@login_required
def account_address_delete(id):
    address = Address.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(address)
    db.session.commit()
    flash('Address deleted successfully.', 'success')
    return redirect(url_for('storefront.account_addresses'))


# ---- Section: Reviews & Newsletter (public write endpoints) ----
# Route: POST /product/<slug>/review  (login_required)
# Submits or updates a review for a product. Rating must be 1-5. New reviews
# default to is_approved=False so an admin must moderate them before they
# appear publicly. Re-submitting an existing review re-moderates it.
@storefront_bp.route('/product/<slug>/review', methods=['POST'])
@login_required
def submit_review(slug):
    product = Product.query.filter_by(slug=slug, is_active=True).first_or_404()
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()
    if not rating or rating < 1 or rating > 5:
        flash('Please select a rating.', 'warning')
        return redirect(url_for('storefront.product_detail', slug=slug))
    existing = Review.query.filter_by(product_id=product.id, user_id=current_user.id).first()
    if existing:
        existing.rating = rating
        existing.comment = comment
        existing.is_approved = False
    else:
        review = Review(product_id=product.id, user_id=current_user.id, rating=rating, comment=comment, is_approved=False)
        db.session.add(review)
    db.session.commit()
    flash('Thank you! Your review is pending approval.', 'success')
    return redirect(url_for('storefront.product_detail', slug=slug))


# Route: POST /newsletter/subscribe  (public)
# Captures an email for the mailing list. Validates format, deduplicates
# existing subscribers, and honors a hidden `next` field for redirect.
@storefront_bp.route('/newsletter/subscribe', methods=['POST'])
def newsletter_subscribe():
    email = request.form.get('email', '').strip().lower()
    next_url = request.form.get('next') or url_for('storefront.index')
    if not email or '@' not in email or '.' not in email.split('@')[-1]:
        flash('Please enter a valid email address.', 'warning')
        return redirect(next_url)
    if not NewsletterSubscriber.query.filter_by(email=email).first():
        db.session.add(NewsletterSubscriber(email=email))
        db.session.commit()
    flash('Welcome to the Gold Circle! You will hear from us soon.', 'success')
    return redirect(next_url)



