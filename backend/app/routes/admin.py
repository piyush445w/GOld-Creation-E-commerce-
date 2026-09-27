"""
Gold Creation - admin back-office blueprint (``/admin``).

This module implements the ``admin`` Flask blueprint: the authentication-gated
back-office CRUD surface for the whole storefront. Every route is protected by
the ``@admin_required`` decorator, so a non-admin authenticated user receives a
bare 404 (the panel is not advertised) and a guest is bounced to the dedicated
admin login page.

Capabilities grouped below:
  * Authentication  - guard behaviour for guests vs. non-admins.
  * Dashboard       - KPI counters, revenue total and the 10 latest orders.
  * Products        - listing/search, create, edit, soft delete.
  * Product media   - binary asset upload, thumbnails, ordering, primary image.
  * Categories      - hierarchical taxonomy CRUD with slug uniquification.
  * Orders          - listing/filter, detail view, status transitions + restock.
  * Coupons         - discount code CRUD with validity window and category scope.
  * Pages           - CMS content pages, publish toggle.
  * Settings        - key/value site settings (hero copy, contact, colours).
  * Banners         - homepage carousel slides with scheduling window.
  * Navigation      - menu item ordering and creation/deletion.
  * Customers       - customer directory and per-customer order history.
  * Reviews         - moderation queue (approve or reject/delete).
  * Media manager   - cross-product asset browser with filters.

Note: this blueprint only manipulates data. Files are never written to the
filesystem - image/video bytes are persisted into MySQL as BLOBs (see
``app.utils.media.save_media_to_db``) and served back through the ``media``
blueprint.
"""
from datetime import datetime
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, session
)
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, DecimalField, IntegerField,
    BooleanField, SelectField, HiddenField, DateTimeField, DateField
)
from wtforms.validators import DataRequired, Optional as WTFOptional, NumberRange
from sqlalchemy import or_
from app import db
from app.models.product import Product
from app.models.category import Category
from app.models.order import Order
from app.models.coupon import Coupon
from app.models.page import Page
from app.models.page_media import PageMedia
from app.models.site_setting import SiteSetting
from app.models.banner import Banner
from app.models.navigation_menu import NavigationMenu
from app.models.product_media import ProductMedia
from app.models.category_media import CategoryMedia
from app.models.user import User
from app.models.review import Review
from app.models.product_variant import ProductVariant
from app.models.site_asset import SiteAsset

# Every admin view/view-function is mounted under the '/admin' url_prefix.
admin_bp = Blueprint('admin', __name__)


# Single access-control decorator for the whole back office.
# Guests -> redirect to the dedicated admin login; logged-in non-admins -> empty
# 404 so the panel's existence is not leaked. Copies __name__ so endpoint names
# stay intact in url_for().
def admin_required(fn):
    def wrapper(*args, **kwargs):
        admin_user_id = session.get('admin_user_id')
        if not admin_user_id:
            return redirect(url_for('auth.admin_login'))
        user = User.query.get(admin_user_id)
        if not user or user.role != 'admin':
            session.pop('admin_user_id', None)
            return '', 404
        from flask import g
        g.admin_user = user
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


# ---------------------------------------------------------------------------
# WTForms
# ---------------------------------------------------------------------------
# Server-side form definitions for the admin create/edit screens. Each form
# mirrors one table; SelectField choices are injected per-request at view time
# so the option lists stay in sync with the database.

# Product editor: core catalogue fields only. Variants (size/colour/stock) are
# submitted separately as a JSON blob in 'variants_data'.
class ProductForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    category_id = SelectField('Category', coerce=int, validators=[DataRequired()])
    description = TextAreaField('Description', validators=[WTFOptional()])
    base_price = DecimalField('Base Price', validators=[DataRequired(), NumberRange(min=0)])
    sku = StringField('SKU', validators=[WTFOptional()])
    is_active = BooleanField('Active', default=True)
    festival_tag = StringField('Festival Tag', validators=[WTFOptional()])
    meta_title = StringField('Meta Title', validators=[WTFOptional()])
    meta_description = StringField('Meta Description', validators=[WTFOptional()])


# Category editor, including self-referencing parent for sub-categories and the
# 'festival collection' flag used by the seasonal storefront sections.
class CategoryForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    slug = StringField('Slug', validators=[WTFOptional()])
    parent_id = SelectField('Parent Category', coerce=lambda x: int(x) if x else None, validators=[WTFOptional()])
    description = TextAreaField('Description', validators=[WTFOptional()])
    image_url = StringField('Image URL', validators=[WTFOptional()])
    is_festival_collection = BooleanField('Festival Collection', default=False)
    display_order = IntegerField('Display Order', default=0)
    is_active = BooleanField('Active', default=True)


# Coupon editor: percent/flat discount, minimum basket value, an optional
# validity window, a total usage cap and an optional category restriction.
class CouponForm(FlaskForm):
    code = StringField('Code', validators=[DataRequired()])
    discount_type = SelectField('Discount Type', choices=[('percent', 'Percent'), ('flat', 'Flat')], validators=[DataRequired()])
    discount_value = DecimalField('Discount Value', validators=[DataRequired(), NumberRange(min=0)])
    min_order_value = DecimalField('Min Order Value', default=0)
    valid_from = DateTimeField('Valid From', format='%Y-%m-%dT%H:%M', validators=[WTFOptional()])
    valid_to = DateTimeField('Valid To', format='%Y-%m-%dT%H:%M', validators=[WTFOptional()])
    usage_limit = IntegerField('Usage Limit', validators=[WTFOptional()])
    is_active = BooleanField('Active', default=True)
    applies_to_category_id = SelectField('Applies To Category', coerce=lambda x: int(x) if x else None, validators=[WTFOptional()])


# CMS page editor. 'is_published' controls whether the public site renders it.
class PageForm(FlaskForm):
    slug = StringField('Slug', validators=[DataRequired()])
    title = StringField('Title', validators=[DataRequired()])
    content = TextAreaField('Content', validators=[DataRequired()])
    meta_title = StringField('Meta Title', validators=[WTFOptional()])
    meta_description = StringField('Meta Description', validators=[WTFOptional()])
    is_published = BooleanField('Published', default=False)


# Carousel slide editor; start_date/end_date gate the slide's visibility window.
class BannerForm(FlaskForm):
    title = StringField('Title', validators=[WTFOptional()])
    image_url = StringField('Image URL', validators=[WTFOptional()])
    link_url = StringField('Link URL', validators=[WTFOptional()])
    display_order = IntegerField('Display Order', default=0)
    is_active = BooleanField('Active', default=True)
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[WTFOptional()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[WTFOptional()])


# Menu item editor; 'target_url_or_page_slug' is either a raw URL or a CMS page
# slug, and 'parent_id' nests the item under another menu entry.
class NavigationItemForm(FlaskForm):
    label = StringField('Label', validators=[DataRequired()])
    target_url_or_page_slug = StringField('URL or Page Slug', validators=[DataRequired()])
    display_order = IntegerField('Display Order', default=0)
    parent_id = SelectField('Parent Menu', coerce=int, validators=[WTFOptional()])
    is_active = BooleanField('Active', default=True)


# Declared for the order status POST form; note the order status handler below
# currently reads request.form directly instead of validating through this form.
class OrderStatusForm(FlaskForm):
    status = HiddenField('Status', validators=[DataRequired()])


# Upload guardrails for the media endpoints: whitelist by extension AND mime
# type, with a 5 MB cap for images and 50 MB for videos.
ALLOWED_IMAGE_EXT = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED_VIDEO_EXT = {'mp4', 'webm'}
ALLOWED_IMAGE_MIME = {'image/png', 'image/jpeg', 'image/webp'}
ALLOWED_VIDEO_MIME = {'video/mp4', 'video/webm'}
MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_VIDEO_SIZE = 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
# Landing page of the panel: single-page KPI overview for the store.

# GET /admin/ and GET /admin/dashboard (both rules point at one view).
# Admin only. Aggregates catalogue/order/customer/review counters plus total
# revenue, then renders admin/dashboard.html with the 10 most recent orders.
@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    # Revenue is the SUM of order totals across every order regardless of
    # status; coalesced to 0 so an empty store renders 0 instead of None.
    total_products = Product.query.count()
    total_orders = Order.query.count()
    total_customers = User.query.filter_by(role='customer').count()
    pending_orders = Order.query.filter_by(status='pending').count()
    pending_reviews = Review.query.filter_by(is_approved=False).count()
    recent_orders = Order.query.order_by(Order.placed_at.desc()).limit(10).all()
    total_revenue = db.session.query(db.func.sum(Order.total)).scalar() or 0
    return render_template(
        'admin/dashboard.html',
        total_products=total_products,
        total_orders=total_orders,
        total_customers=total_customers,
        pending_orders=pending_orders,
        pending_reviews=pending_reviews,
        recent_orders=recent_orders,
        total_revenue=total_revenue,
    )

# ---- Section: Products ----
# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
# Catalogue CRUD. Products are the anchor of the whole data model: they own
# variants (size/colour/stock), media assets, reviews, wishlist entries and order
# line items. Deletion is soft (is_active = False) so order history stays intact.

# GET /admin/products (admin only) - paginated catalogue list, 20 per page, with
# an optional '?q=' term matched case-insensitively against name and SKU.
# Renders admin/products.html.


@admin_bp.route('/products')
@admin_required
def products_list():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '', type=str)
    query = Product.query
    # Free-text search spans both the customer-facing name and the stock-keeping
    # unit, so admins can find an item by either identifier.
    if search:
        query = query.filter(or_(Product.name.ilike(f'%{search}%'), Product.sku.ilike(f'%{search}%')))
    # Newest first; error_out=False keeps out-of-range page numbers on page 1
    # instead of raising a 404.
    products = query.order_by(Product.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/products.html', products=products, search=search)


# GET|POST /admin/products/new - admin only. Renders the empty product form and,
# on a valid POST, creates the product plus its variant rows. Redirects to the
# product list on success.
@admin_bp.route('/products/new', methods=['GET', 'POST'])
@admin_required
def product_new():
    form = ProductForm()
    # Category dropdown is rebuilt on every request from live data, ordered by
    # the merchandising display_order.
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by(Category.display_order).all()]
    if form.validate_on_submit():
        # Slug uniquification: derive a URL slug from the name, then append an
        # incrementing -1, -2, ... suffix until the slug column is free.
        base_slug = form.name.data.lower().replace(' ', '-')
        slug = Product.query.filter_by(slug=base_slug).first()
        suffix = 1
        while slug:
            base_slug = f"{form.name.data.lower().replace(' ', '-')}-{suffix}"
            slug = Product.query.filter_by(slug=base_slug).first()
            suffix += 1
        # SKU is a unique column, so pre-check it to give a friendly message
        # instead of an IntegrityError. It is optional.
        if form.sku.data:
            existing_sku = Product.query.filter_by(sku=form.sku.data).first()
            if existing_sku:
                flash('A product with this SKU already exists.', 'danger')
                return render_template('admin/product_form.html', form=form, categories=Category.query.order_by(Category.display_order).all())
        # Create the parent product first: variants need the generated id.
        product = Product(
            name=form.name.data,
            category_id=form.category_id.data,
            description=form.description.data,
            base_price=form.base_price.data,
            sku=form.sku.data,
            is_active=form.is_active.data,
            festival_tag=form.festival_tag.data,
            meta_title=form.meta_title.data,
            meta_description=form.meta_description.data,
            slug=base_slug,
        )
        db.session.add(product)
        db.session.commit()
        # The variant grid is serialised by the admin template into a single
        # 'variants_data' JSON array field, since variants are dynamic rows and
        # cannot be expressed as static WTForm fields.
        variants_data = request.form.get('variants_data')
        if variants_data:
            import json
            try:
                variants = json.loads(variants_data)
            except (json.JSONDecodeError, TypeError):
                # Malformed payload: keep the product (already committed) and
                # bounce the admin to the edit screen to retry the variants.
                flash('Invalid variants data format.', 'danger')
                return redirect(url_for('admin.product_edit', id=product.id))
            # Insert one ProductVariant per JSON object; price_override of 0/'' is
            # normalised to None so the variant falls back to the base price.
            for v in variants:
                variant = ProductVariant(
                    product_id=product.id,
                    size=v.get('size', ''),
                    color=v.get('color', ''),
                    sku=v.get('sku', ''),
                    price_override=v.get('price_override') or None,
                    stock_quantity=int(v.get('stock_quantity', 0)),
                    image_url=v.get('image_url', ''),
                )
                db.session.add(variant)
            db.session.commit()
        flash('Product created successfully.', 'success')
        return redirect(url_for('admin.products_list'))
    # GET (or a re-rendered invalid POST) shows the blank editor.
    return render_template('admin/product_form.html', form=form, categories=Category.query.order_by(Category.display_order).all())

# GET|POST /admin/products/<id>/edit - admin only. Loads the product, updates all
# core fields and syncs the variant grid (create/update/delete). Redirects to the
# product list on success; 404 for an unknown id.


@admin_bp.route('/products/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def product_edit(id):
    # get_or_404 turns a missing product id into a standard HTTP 404.
    product = Product.query.get_or_404(id)
    # obj= pre-populates the form from the model for the GET render.
    form = ProductForm(obj=product)
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by(Category.display_order).all()]
    if form.validate_on_submit():
        product.name = form.name.data
        # Slug uniquification, but skipping the product's own current slug so an
        # unchanged name does not gain a suffix on every save.
        base_slug = form.name.data.lower().replace(' ', '-')
        existing = Product.query.filter_by(slug=base_slug).first()
        suffix = 1
        while existing and existing.id != product.id:
            base_slug = f"{form.name.data.lower().replace(' ', '-')}-{suffix}"
            existing = Product.query.filter_by(slug=base_slug).first()
            suffix += 1
        # Same duplicate-SKU guard as create, again ignoring this product itself.
        if form.sku.data:
            existing_sku = Product.query.filter_by(sku=form.sku.data).first()
            if existing_sku and existing_sku.id != product.id:
                flash('A product with this SKU already exists.', 'danger')
                return render_template('admin/product_form.html', form=form, product=product, categories=Category.query.order_by(Category.display_order).all())
        # Field-by-field assignment keeps the existing row (and its id/timestamps).
        product.slug = base_slug
        product.category_id = form.category_id.data
        product.description = form.description.data
        product.base_price = form.base_price.data
        product.sku = form.sku.data
        product.is_active = form.is_active.data
        product.festival_tag = form.festival_tag.data
        product.meta_title = form.meta_title.data
        product.meta_description = form.meta_description.data
        db.session.commit()
        # Optional variant sync, driven by the same JSON array as the create view.
        variants_data = request.form.get('variants_data')
        if variants_data:
            import json
            try:
                variants = json.loads(variants_data)
            except (json.JSONDecodeError, TypeError):
                flash('Invalid variants data format.', 'danger')
                return redirect(url_for('admin.product_edit', id=product.id))
            for v in variants:
                # A JSON object carrying an 'id' is an existing row -> patch it
                # in place (scoped by product_id to prevent cross-product edits).
                if v.get('id'):
                    variant = ProductVariant.query.filter_by(id=v['id'], product_id=product.id).first()
                    if variant:
                        variant.size = v.get('size', variant.size)
                        variant.color = v.get('color', variant.color)
                        variant.sku = v.get('sku', variant.sku)
                        variant.price_override = v.get('price_override') or None
                        variant.stock_quantity = int(v.get('stock_quantity', variant.stock_quantity))
                        variant.image_url = v.get('image_url', variant.image_url)
                else:
                    # No 'id' -> a newly added grid row.
                    variant = ProductVariant(
                        product_id=product.id,
                        size=v.get('size', ''),
                        color=v.get('color', ''),
                        sku=v.get('sku', ''),
                        price_override=v.get('price_override') or None,
                        stock_quantity=int(v.get('stock_quantity', 0)),
                        image_url=v.get('image_url', ''),
                    )
                    db.session.add(variant)
            # The grid also posts a JSON array of the row ids it removed, which
            # is how variant deletion happens (there is no separate bulk action).
            deleted_ids = request.form.get('deleted_variant_ids', '')
            if deleted_ids:
                import json as json2
                try:
                    deleted_ids_list = json2.loads(deleted_ids)
                except (json.JSONDecodeError, TypeError):
                    deleted_ids_list = []
                # Rows the grid removed. Bulk delete is scoped by product_id so
                # a tampered payload cannot delete another product's variants.
                for did in deleted_ids_list:
                    ProductVariant.query.filter_by(id=did, product_id=product.id).delete()
            db.session.commit()
        flash('Product updated successfully.', 'success')
        return redirect(url_for('admin.products_list'))
    return render_template('admin/product_form.html', form=form, product=product, categories=Category.query.order_by(Category.display_order).all())


# POST /admin/products/<id>/delete - admin only. Soft delete: flips is_active to
# False so the product disappears from the storefront while existing order line
# items keep their foreign keys. Redirects to the product list.
@admin_bp.route('/products/<int:id>/delete', methods=['POST'])
@admin_required
def product_delete(id):
    product = Product.query.get_or_404(id)
    # Soft delete rather than db.session.delete - products are referenced by
    # order_items, reviews, wishlist and media rows.
    product.is_active = False
    db.session.commit()
    flash('Product deleted successfully.', 'success')
    return redirect(url_for('admin.products_list'))


# ---- Section: Product Media (per-product assets) ----
# ---------------------------------------------------------------------------
# Product Media
# ---------------------------------------------------------------------------
# Binary asset management. Images and videos are stored as MySQL BLOBs, not on
# disk; the public site fetches them back through the 'media' blueprint using the
# media_url / thumbnail_url produced here.


# Shared upload helper: delegates validation (extension, mime, size cap) and
# BLOB persistence to app.utils.media, flashing the error and returning None so
# the calling handler can continue with its remaining files.
def _save_upload(file, media_type):
    if not file or file.filename == '':
        return None
    from app.utils.media import save_media_to_db
    result, err = save_media_to_db(file, media_type)
    if err:
        flash(err, 'danger')
        return None
    return result

# POST /admin/products/<product_id>/media - admin only. Accepts a multi-file
# 'file' field plus a 'media_type' hint, creates one ProductMedia row per accepted
# file and redirects back to the product editor with a success/warning flash.


@admin_bp.route('/products/<int:product_id>/media', methods=['POST'])
@admin_required
def product_media_upload(product_id):
    product = Product.query.get_or_404(product_id)
    files = request.files.getlist('file')
    media_type_raw = request.form.get('media_type', 'image')
    # Whitelist the type: anything other than an explicit 'video' is forced to
    # 'image', matching the CHECK constraint on product_media.media_type.
    media_type = 'image' if media_type_raw not in ('video',) else 'video'
    uploaded = 0
    # Partial success is allowed: each file is validated and committed on its own,
    # so one bad file does not discard the rest of the batch.
    for file in files:
        if not file or file.filename == '':
            continue
        stored = _save_upload(file, media_type)
        if stored:
            media = ProductMedia(
                product_id=product.id,
                media_type=media_type,
                # media_url is NOT NULL, so it is first written as a placeholder,
                # then replaced once the row has an id to build the URL from.
                media_url='',
                mime_type=stored['mime_type'],
                # New assets are appended to the end of the gallery.
                display_order=ProductMedia.query.filter_by(product_id=product.id).count(),
                media_data=stored['data'],
                file_size=stored['file_size'],
                original_filename=stored['original_filename'],
                checksum=stored['checksum'],
            )
            db.session.add(media)
            # Commit once to obtain media.id, then store the serving URL that the
            # storefront uses and commit again.
            db.session.commit()
            media.media_url = url_for('media.serve_product_media', product_id=product.id, media_id=media.id, _external=False)
            db.session.commit()
            uploaded += 1
    # Single summary flash for the whole batch, then back to the product editor.
    if uploaded:
        flash(f'{uploaded} file(s) uploaded successfully.', 'success')
    else:
        flash('No files uploaded.', 'warning')
    return redirect(url_for('admin.product_edit', id=product.id))


# POST /admin/products/<product_id>/media/<media_id>/thumbnail - admin only.
# Replaces the thumbnail BLOB for one media row. Called by JS, so it answers with
# JSON ({'success', 'thumbnail_url'}) and HTTP 400 on validation failure.
@admin_bp.route('/products/<int:product_id>/media/<int:media_id>/thumbnail', methods=['POST'])
@admin_required
def product_media_set_thumbnail(product_id, media_id):
    # Ownership check: the media row must belong to the product in the URL.
    media = ProductMedia.query.filter_by(id=media_id, product_id=product_id).first_or_404()
    file = request.files.get('thumbnail')
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': 'No thumbnail file provided.'}), 400
    # Cheap pre-filter on the extension before doing the more expensive
    # mime/size validation inside save_media_to_db.
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_IMAGE_EXT:
        return jsonify({'success': False, 'message': 'Invalid image extension.'}), 400
    from app.utils.media import save_media_to_db
    stored, err = save_media_to_db(file, 'image')
    if err:
        return jsonify({'success': False, 'message': err}), 400
    # Thumbnail bytes are stored alongside the media, not replacing it.
    media.thumbnail_data = stored['data']
    media.thumbnail_url = url_for('media.serve_thumbnail', media_id=media.id, _external=False)
    db.session.commit()
    return jsonify({'success': True, 'thumbnail_url': media.thumbnail_url})


# DELETE /admin/products/<product_id>/media/<media_id> - admin only. Hard-deletes
# one asset (no soft flag on media) and closes the gap in the gallery ordering.
# Returns a JSON success message; 404 if the id is not owned by the product.
@admin_bp.route('/products/<int:product_id>/media/<int:media_id>', methods=['DELETE'])
@admin_required
def product_media_delete(product_id, media_id):
    media = ProductMedia.query.filter_by(id=media_id, product_id=product_id).first_or_404()
    deleted_order = media.display_order
    db.session.delete(media)
    # Keep display_order contiguous by shifting every later item down one slot,
    # preserving the admin-defined gallery sequence.
    remaining_media = ProductMedia.query.filter(ProductMedia.product_id == product_id, ProductMedia.display_order > deleted_order).all()
    for m in remaining_media:
        m.display_order -= 1
    db.session.commit()
    return jsonify({'success': True, 'message': 'Media deleted successfully.'})


# POST /admin/products/<product_id>/media/reorder - admin only. Drag-and-drop
# gallery ordering: rewrites display_order from the submitted id sequence.
# Accepts a JSON body or a form post; returns JSON, 400 on an empty/invalid list.
@admin_bp.route('/products/<int:product_id>/media/reorder', methods=['POST'])
@admin_required
def product_media_reorder(product_id):
    # The JS reorder widget posts JSON, but a form post is accepted as a fallback.
    data = request.get_json(silent=True) or request.form
    media_ids = data.get('media_ids', [])
    if not media_ids:
        return jsonify({'success': False, 'message': 'No media IDs provided.'}), 400
    # Coerce to int up front so a malformed id cannot reach the query layer.
    try:
        media_ids = [int(mid) for mid in media_ids]
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid media IDs.'}), 400
    # The submitted order becomes display_order 0..n-1; ids not owned by this
    # product are silently ignored.
    for index, media_id in enumerate(media_ids):
        media = ProductMedia.query.filter_by(id=media_id, product_id=product_id).first()
        if media:
            media.display_order = index
    db.session.commit()
    return jsonify({'success': True, 'message': 'Media reordered successfully.'})


# POST /admin/products/<product_id>/media/<media_id>/primary - admin only. Marks
# one asset as the product's main image (Product.primary_image reads is_primary
# first). Returns JSON; clears the previous primary in the same transaction.
@admin_bp.route('/products/<int:product_id>/media/<int:media_id>/primary', methods=['POST'])
@admin_required
def product_media_set_primary(product_id, media_id):
    media = ProductMedia.query.filter_by(id=media_id, product_id=product_id).first_or_404()
    # Enforce the single-primary invariant with one bulk UPDATE, then set the new one.
    ProductMedia.query.filter_by(product_id=product_id, is_primary=True).update({'is_primary': False})
    media.is_primary = True
    db.session.commit()
    return jsonify({'success': True, 'message': 'Primary media updated successfully.'})


# DELETE /admin/products/<product_id>/variants/<variant_id> - admin only. Single
# variant removal for the product editor's inline grid; returns JSON. Note this
# does not rewrite the remaining variant display order.
@admin_bp.route('/products/<int:product_id>/variants/<int:variant_id>', methods=['DELETE'])
@admin_required
def product_variant_delete(product_id, variant_id):
    variant = ProductVariant.query.filter_by(id=variant_id, product_id=product_id).first_or_404()
    db.session.delete(variant)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Variant deleted successfully.'})

# ---- Section: Categories ----
# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
# Hierarchical taxonomy (self-referencing parent_id) that drives the storefront
# mega-menu and product filtering. Deletion is soft (is_active = False).

# GET /admin/categories - admin only. Paginated (20/page) tree listing ordered by
# display_order then recency; renders admin/categories.html.


@admin_bp.route('/categories')
@admin_required
def categories_list():
    page = request.args.get('page', 1, type=int)
    categories = Category.query.order_by(Category.display_order, Category.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/categories.html', categories=categories.items, pagination=categories)


# GET|POST /admin/categories/new - admin only. Creates a top-level or nested
# category. Redirects to the category list on success.
@admin_bp.route('/categories/new', methods=['GET', 'POST'])
@admin_required
def category_new():
    form = CategoryForm()
    # The empty choice means "no parent"; the coerce lambda maps '' to None.
    form.parent_id.choices = [('', '-- None --')] + [(c.id, c.name) for c in Category.query.order_by(Category.display_order).all()]
    if form.validate_on_submit():
        # Slug is generated from the name (spaces -> dashes) and de-duplicated with
        # a -1, -2, ... suffix against the unique slug column.
        base_slug = form.name.data.lower().replace(' ', '-').strip('/')
        slug = base_slug
        suffix = 1
        existing = Category.query.filter_by(slug=slug).first()
        while existing:
            slug = f"{base_slug}-{suffix}"
            existing = Category.query.filter_by(slug=slug).first()
            suffix += 1
        # No parent selected -> NULL (root level of the tree).
        parent_id = form.parent_id.data if form.parent_id.data else None
        category = Category(
            name=form.name.data,
            slug=slug,
            parent_id=parent_id,
            description=form.description.data,
            image_url=form.image_url.data,
            is_festival_collection=form.is_festival_collection.data,
            display_order=form.display_order.data,
            is_active=form.is_active.data,
        )
        db.session.add(category)
        db.session.commit()
        flash('Category created successfully.', 'success')
        return redirect(url_for('admin.categories_list'))
    return render_template('admin/category_form.html', form=form)


# GET|POST /admin/categories/<id>/edit - admin only. Updates a category in place,
# including re-parenting. The category itself is excluded from the parent
# dropdown to avoid making a node its own parent. Redirects to the list.
@admin_bp.route('/categories/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def category_edit(id):
    category = Category.query.get_or_404(id)
    form = CategoryForm(obj=category)
    # Exclude self from the parent choices (only a direct self-reference is
    # blocked; a full descendant-cycle check is not performed here).
    form.parent_id.choices = [('', '-- None --')] + [(c.id, c.name) for c in Category.query.filter(Category.id != id).order_by(Category.display_order).all()]
    if form.validate_on_submit():
        category.name = form.name.data
        # Slug re-derived from the name and de-duplicated, ignoring this row.
        base_slug = form.name.data.lower().replace(' ', '-').strip('/')
        slug = base_slug
        existing = Category.query.filter_by(slug=slug).first()
        suffix = 1
        while existing and existing.id != category.id:
            slug = f"{base_slug}-{suffix}"
            existing = Category.query.filter_by(slug=slug).first()
            suffix += 1
        category.slug = slug
        category.parent_id = form.parent_id.data if form.parent_id.data else None
        category.description = form.description.data
        category.image_url = form.image_url.data
        category.is_festival_collection = form.is_festival_collection.data
        category.display_order = form.display_order.data
        category.is_active = form.is_active.data
        db.session.commit()
        flash('Category updated successfully.', 'success')
        return redirect(url_for('admin.categories_list'))
    return render_template('admin/category_form.html', form=form, category=category)


# POST /admin/categories/<id>/delete - admin only. Soft delete (is_active = False)
# so existing products keep a valid category reference. Redirects to the list.
@admin_bp.route('/categories/<int:id>/delete', methods=['POST'])
@admin_required
def category_delete(id):
    category = Category.query.get_or_404(id)
    # Soft delete: products FK to categories, so the row itself is kept.
    category.is_active = False
    db.session.commit()
    flash('Category deleted successfully.', 'success')
    return redirect(url_for('admin.categories_list'))

# ---- Section: Category Media ----
# ---------------------------------------------------------------------------
# Category Media
# ---------------------------------------------------------------------------
# Binary asset management for category galleries. Images and videos are stored
# as MySQL BLOBs, not on disk; the public site fetches them back through the
# media blueprint using the media_url produced here.

# POST /admin/categories/<category_id>/media - admin only. Accepts a multi-file
# file field plus a media_type hint, creates one CategoryMedia row per accepted
# file and redirects back to the category editor with a success flash.


@admin_bp.route('/categories/<int:category_id>/media', methods=['POST'])
@admin_required
def category_media_upload(category_id):
    category = Category.query.get_or_404(category_id)
    files = request.files.getlist('file')
    media_type_raw = request.form.get('media_type', 'image')
    media_type = 'image' if media_type_raw not in ('video',) else 'video'
    for file in files:
        if not file or file.filename == '':
            continue
        from app.utils.media import save_media_to_db
        result, err = save_media_to_db(file, media_type)
        if err:
            flash(err, 'danger')
            continue
        media = CategoryMedia(
            category_id=category.id,
            media_type=media_type,
            media_url='',
            mime_type=result['mime_type'],
            display_order=CategoryMedia.query.filter_by(category_id=category.id).count(),
            media_data=result['data'],
            file_size=result['file_size'],
            original_filename=result['original_filename'],
            checksum=result['checksum'],
        )
        db.session.add(media)
        db.session.commit()
        media.media_url = url_for('media.serve_category_media', category_id=category.id, media_id=media.id, _external=False)
        db.session.commit()
    flash('Media uploaded successfully.', 'success')
    return redirect(url_for('admin.category_edit', id=category.id))

# POST /admin/categories/<category_id>/media/<media_id>/delete - admin only.
# Hard-deletes one asset and redirects back to the category editor.


@admin_bp.route('/categories/<int:category_id>/media/<int:media_id>/delete', methods=['POST'])
@admin_required
def category_media_delete(category_id, media_id):
    media = CategoryMedia.query.filter_by(id=media_id, category_id=category_id).first_or_404()
    db.session.delete(media)
    db.session.commit()
    flash('Media deleted successfully.', 'success')
    return redirect(url_for('admin.category_edit', id=category_id))

# POST /admin/categories/<category_id>/media/<media_id>/primary - admin only.
# Marks one asset as the category primary image.


@admin_bp.route('/categories/<int:category_id>/media/<int:media_id>/primary', methods=['POST'])
@admin_required
def category_media_set_primary(category_id, media_id):
    media = CategoryMedia.query.filter_by(id=media_id, category_id=category_id).first_or_404()
    CategoryMedia.query.filter_by(category_id=category_id).update({'is_primary': False})
    media.is_primary = True
    db.session.commit()
    flash('Primary media updated.', 'success')
    return redirect(url_for('admin.category_edit', id=category_id))

# POST /admin/categories/<category_id>/media/reorder - admin only.
# Drag-and-drop gallery ordering: rewrites display_order from submitted id sequence.


@admin_bp.route('/categories/<int:category_id>/media/reorder', methods=['POST'])
@admin_required
def category_media_reorder(category_id):
    order = request.form.get('order', '')
    ids = [int(x) for x in order.split(',') if x.strip().isdigit()]
    for index, media_id in enumerate(ids):
        media = CategoryMedia.query.filter_by(id=media_id, category_id=category_id).first()
        if media:
            media.display_order = index
    db.session.commit()
    return jsonify({'success': True})


# POST /admin/categories/<int:category_id>/image - admin only.
# Accepts an image file, stores it as a CategoryMedia row, marks it primary,
# and updates category.image_url. Returns JSON.
@admin_bp.route('/categories/<int:category_id>/image', methods=['POST'])
@admin_required
def category_image_upload(category_id):
    category = Category.query.get_or_404(category_id)
    file = request.files.get('image')
    if not file or file.filename == '':
        return jsonify({'success': False, 'error': 'No image file provided.'}), 400
    from app.utils.media import save_media_to_db
    stored, err = save_media_to_db(file, 'image')
    if err:
        return jsonify({'success': False, 'error': err}), 400
    media = CategoryMedia(
        category_id=category.id,
        media_type='image',
        media_url='',
        mime_type=stored['mime_type'],
        display_order=CategoryMedia.query.filter_by(category_id=category.id).count(),
        media_data=stored['data'],
        file_size=stored['file_size'],
        original_filename=stored['original_filename'],
        checksum=stored['checksum'],
    )
    db.session.add(media)
    db.session.commit()
    media.media_url = url_for('media.serve_category_media', category_id=category.id, media_id=media.id, _external=False)
    CategoryMedia.query.filter_by(category_id=category_id).update({'is_primary': False})
    media.is_primary = True
    category.image_url = media.media_url
    db.session.commit()
    return jsonify({'success': True, 'image_url': category.image_url})


# ---- Section: Orders ----
# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
# Order fulfilment. Read-only views over customer orders plus the single
# lifecycle transition admins can perform. Order totals/currency are not editable
# here; only Order.status changes, plus automatic restock on cancel/refund.

# GET /admin/orders - admin only. Paginated order table, newest first, with an
# optional '?status=' filter. Renders admin/orders.html.
@admin_bp.route('/orders')
@admin_required
def orders_list():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '', type=str)
    query = Order.query
    # Empty status means "all"; otherwise exact match on the status column.
    if status_filter:
        query = query.filter(Order.status == status_filter)
    orders = query.order_by(Order.placed_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/orders.html', orders=orders.items, pagination=orders, status_filter=status_filter)


# GET /admin/orders/<id> - admin only. Full order view: line items, shipping
# address, payment/currency info and the status form. Renders
# admin/order_detail.html; 404 for an unknown id.
@admin_bp.route('/orders/<int:id>')
@admin_required
def order_detail(id):
    order = Order.query.get_or_404(id)
    return render_template('admin/order_detail.html', order=order)


# POST /admin/orders/<id>/status - admin only. Applies a status transition from a
# hidden form field and redirects back to the order detail page either way.
@admin_bp.route('/orders/<int:id>/status', methods=['POST'])
@admin_required
def order_update_status(id):
    order = Order.query.get_or_404(id)
    new_status = request.form.get('status', '').strip()
    # Whitelist: the status column is a free-form string, so allowed values are
    # enforced here rather than in the model.
    valid_statuses = ['pending', 'paid', 'shipped', 'delivered', 'cancelled', 'refunded']
    if new_status not in valid_statuses:
        flash('Invalid status selected.', 'danger')
    else:
        # Cancelling or refunding returns the ordered units to variant stock.
        # Guarded on the previous status so a repeated cancel/refund does not
        # double-credit inventory.
        restock_statuses = ('cancelled', 'refunded')
        if new_status in restock_statuses and order.status not in restock_statuses:
            for item in order.items:
                # Items whose variant was since deleted cannot be restocked.
                if item.variant:
                    item.variant.stock_quantity += item.quantity
        order.status = new_status
        # Single commit covers both the status change and the restock updates.
        db.session.commit()
        flash('Order status updated successfully.', 'success')
    return redirect(url_for('admin.order_detail', id=order.id))

# ---- Section: Coupons ----
# ---------------------------------------------------------------------------
# Coupons
# ---------------------------------------------------------------------------
# Discount code administration. The checkout flow reads these rows to validate
# the window (valid_from/valid_to), usage cap and optional category scope.

# GET /admin/coupons - admin only. Paginated (20/page) coupon table, newest
# first. Renders admin/coupons.html.


@admin_bp.route('/coupons')
@admin_required
def coupons_list():
    page = request.args.get('page', 1, type=int)
    coupons = Coupon.query.order_by(Coupon.id.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/coupons.html', coupons=coupons.items, pagination=coupons)


# GET|POST /admin/coupons/new - admin only. Creates a coupon. The code is
# normalised to upper case and must be unique. Redirects to the coupon list.
@admin_bp.route('/coupons/new', methods=['GET', 'POST'])
@admin_required
def coupon_new():
    form = CouponForm()
    # Optional category scope: '' means the coupon applies to the whole catalogue.
    form.applies_to_category_id.choices = [('', '-- None --')] + [(c.id, c.name) for c in Category.query.order_by(Category.display_order).all()]
    if form.validate_on_submit():
        # Normalise then check uniqueness to avoid an IntegrityError on the
        # unique code column.
        code = form.code.data.strip().upper()
        existing = Coupon.query.filter_by(code=code).first()
        if existing:
            flash('A coupon with this code already exists.', 'danger')
            return render_template('admin/coupon_form.html', form=form)
        applies_to_category_id = form.applies_to_category_id.data if form.applies_to_category_id.data else None
        coupon = Coupon(

            code=code,
            discount_type=form.discount_type.data,
            discount_value=form.discount_value.data,
            min_order_value=form.min_order_value.data or 0,
            valid_from=form.valid_from.data,
            valid_to=form.valid_to.data,
            usage_limit=form.usage_limit.data,
            is_active=form.is_active.data,
            applies_to_category_id=applies_to_category_id,
        )
        db.session.add(coupon)
        db.session.commit()
        flash('Coupon created successfully.', 'success')
        return redirect(url_for('admin.coupons_list'))
    return render_template('admin/coupon_form.html', form=form)


# GET|POST /admin/coupons/<id>/edit - admin only. Updates discount settings.
# The code and times_used are intentionally not editable here: the code is the
# customer-facing identifier and times_used is maintained by checkout. Redirects
# to the coupon list.
@admin_bp.route('/coupons/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def coupon_edit(id):
    coupon = Coupon.query.get_or_404(id)
    form = CouponForm(obj=coupon)
    form.applies_to_category_id.choices = [('', '-- None --')] + [(c.id, c.name) for c in Category.query.order_by(Category.display_order).all()]
    if form.validate_on_submit():
        # Empty min_order_value is stored as 0 (no minimum basket).
        coupon.discount_type = form.discount_type.data
        coupon.discount_value = form.discount_value.data
        coupon.min_order_value = form.min_order_value.data or 0
        coupon.valid_from = form.valid_from.data
        coupon.valid_to = form.valid_to.data
        coupon.usage_limit = form.usage_limit.data
        coupon.is_active = form.is_active.data
        coupon.applies_to_category_id = form.applies_to_category_id.data if form.applies_to_category_id.data else None
        db.session.commit()
        flash('Coupon updated successfully.', 'success')
        return redirect(url_for('admin.coupons_list'))
    return render_template('admin/coupon_form.html', form=form, coupon=coupon)


# POST /admin/coupons/<id>/delete - admin only. Hard delete - coupons have no
# soft flag and no other table references them. Redirects to the coupon list.
@admin_bp.route('/coupons/<int:id>/delete', methods=['POST'])
@admin_required
def coupon_delete(id):
    coupon = Coupon.query.get_or_404(id)
    db.session.delete(coupon)
    db.session.commit()
    flash('Coupon deleted successfully.', 'success')
    return redirect(url_for('admin.coupons_list'))

# ---- Section: CMS Pages ----
# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
# Content pages (About, Shipping Policy, contact, etc.) served on the storefront
# by slug. Only is_published pages are reachable publicly.

# GET /admin/pages - admin only. Paginated (20/page) CMS page list, newest
# first. Renders admin/pages.html.


@admin_bp.route('/pages')
@admin_required
def pages_list():
    page = request.args.get('page', 1, type=int)
    pages = Page.query.order_by(Page.id.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/pages.html', pages=pages.items, pagination=pages)


# GET|POST /admin/pages/new - admin only. Creates a CMS page. The admin-supplied
# slug is normalised (trimmed, lower-cased, spaces to dashes) and must be unique.
# Redirects to the page list on success.
@admin_bp.route('/pages/new', methods=['GET', 'POST'])
@admin_required
def page_new():
    form = PageForm()
    if form.validate_on_submit():
        # Slug becomes the public URL segment, so normalise before the uniqueness
        # check against the unique column.
        slug = form.slug.data.strip().lower().replace(' ', '-')
        existing = Page.query.filter_by(slug=slug).first()
        if existing:
            flash('A page with this slug already exists.', 'danger')
            return render_template('admin/page_form.html', form=form)
        page = Page(
            slug=slug,
            title=form.title.data,
            content=form.content.data,
            meta_title=form.meta_title.data,
            meta_description=form.meta_description.data,
            # Unpublished by default is up to the admin via the checkbox; the
            # field's own default is False.
            is_published=form.is_published.data,
        )
        db.session.add(page)
        db.session.commit()
        flash('Page created successfully.', 'success')
        return redirect(url_for('admin.pages_list'))
    return render_template('admin/page_form.html', form=form)


# GET|POST /admin/pages/<id>/edit - admin only. Updates page content and SEO
# metadata, re-checking slug uniqueness while ignoring the page itself.
# Redirects to the page list.
@admin_bp.route('/pages/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def page_edit(id):
    page = Page.query.get_or_404(id)
    form = PageForm(obj=page)
    if form.validate_on_submit():
        # Same slug normalisation/uniqueness rule as create.
        slug = form.slug.data.strip().lower().replace(' ', '-')
        existing = Page.query.filter_by(slug=slug).first()
        if existing and existing.id != page.id:
            flash('A page with this slug already exists.', 'danger')
            return render_template('admin/page_form.html', form=form, page=page)
        page.slug = slug
        page.title = form.title.data
        page.content = form.content.data
        page.meta_title = form.meta_title.data
        page.meta_description = form.meta_description.data
        page.is_published = form.is_published.data
        db.session.commit()
        flash('Page updated successfully.', 'success')
        return redirect(url_for('admin.pages_list'))
    return render_template('admin/page_form.html', form=form, page=page)


# POST /admin/pages/<id>/toggle - admin only. One-click publish/unpublish
# straight from the list (no form round-trip). Redirects to the page list.
@admin_bp.route('/pages/<int:id>/toggle', methods=['POST'])
@admin_required
def page_toggle(id):
    page = Page.query.get_or_404(id)
    # Flip the flag; updated_at is refreshed automatically by the column's
    # onupdate handler.
    page.is_published = not page.is_published
    db.session.commit()
    flash('Page updated successfully.', 'success')
    return redirect(url_for('admin.pages_list'))


# POST /admin/pages/<id>/delete - admin only. Hard delete of a CMS page (the
# page is referenced only by its slug in navigation labels, not by a FK).
# Redirects to the page list.
@admin_bp.route('/pages/<int:id>/delete', methods=['POST'])
@admin_required
def page_delete(id):
    page = Page.query.get_or_404(id)
    db.session.delete(page)
    db.session.commit()
    flash('Page deleted successfully.', 'success')
    return redirect(url_for('admin.pages_list'))


# POST /admin/pages/<page_id>/media - admin only. Accepts a multi-file
# 'file' field, creates one PageMedia row per accepted file and redirects
# back to the page editor with a success flash.
@admin_bp.route('/pages/<int:page_id>/media', methods=['POST'])
@admin_required
def page_media_upload(page_id):
    page = Page.query.get_or_404(page_id)
    files = request.files.getlist('file')
    media_type = request.form.get('media_type', 'image')
    uploaded = 0
    for file in files:
        if not file or file.filename == '':
            continue
        stored = _save_upload(file, media_type)
        if stored:
            media = PageMedia(
                page_id=page.id,
                media_type=media_type,
                media_url='',
                mime_type=stored['mime_type'],
                display_order=PageMedia.query.filter_by(page_id=page.id).count(),
                media_data=stored['data'],
                file_size=stored['file_size'],
                original_filename=stored['original_filename'],
                checksum=stored['checksum'],
            )
            db.session.add(media)
            db.session.commit()
            media.media_url = url_for('media.serve_page_media', page_id=page.id, media_id=media.id, _external=False)
            db.session.commit()
            uploaded += 1
    if uploaded:
        flash(f'{uploaded} file(s) uploaded successfully.', 'success')
    else:
        flash('No files uploaded.', 'warning')
    return redirect(url_for('admin.page_edit', id=page.id))


# POST /admin/pages/<page_id>/media/<media_id>/delete - admin only.
# Hard-deletes one asset and redirects back to the page editor.
@admin_bp.route('/pages/<int:page_id>/media/<int:media_id>/delete', methods=['POST'])
@admin_required
def page_media_delete(page_id, media_id):
    media = PageMedia.query.filter_by(id=media_id, page_id=page_id).first_or_404()
    db.session.delete(media)
    db.session.commit()
    flash('Media deleted successfully.', 'success')
    return redirect(url_for('admin.page_edit', id=page_id))


# POST /admin/pages/<page_id>/media/<media_id>/primary - admin only.
# Marks one asset as the page primary image.
@admin_bp.route('/pages/<int:page_id>/media/<int:media_id>/primary', methods=['POST'])
@admin_required
def page_media_set_primary(page_id, media_id):
    media = PageMedia.query.filter_by(id=media_id, page_id=page_id).first_or_404()
    PageMedia.query.filter_by(page_id=page_id).update({'is_primary': False})
    media.is_primary = True
    db.session.commit()
    flash('Primary media updated.', 'success')
    return redirect(url_for('admin.page_edit', id=page_id))


# POST /admin/pages/<page_id>/media/reorder - admin only.
# Drag-and-drop gallery ordering: rewrites display_order from submitted id sequence.
@admin_bp.route('/pages/<int:page_id>/media/reorder', methods=['POST'])
@admin_required
def page_media_reorder(page_id):
    order = request.form.get('order', '')
    ids = [int(x) for x in order.split(',') if x.strip().isdigit()]
    for index, media_id in enumerate(ids):
        media = PageMedia.query.filter_by(id=media_id, page_id=page_id).first()
        if media:
            media.display_order = index
    db.session.commit()
    return jsonify({'success': True})


# ---- Section: Settings ----
# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
# Key/value site configuration rendered by the public templates: hero copy,
# announcement bar, footer text, theme accent colours and contact details.

# GET|POST /admin/settings - admin only. Renders admin/settings.html with the
# current values on GET; on POST upserts the whitelisted keys and redirects back
# to the same page with a success flash.
@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings_view():
    if request.method == 'POST':
        logo_file = request.files.get('logo')
        if logo_file and logo_file.filename != '':
            from app.utils.media import save_media_to_db
            stored, err = save_media_to_db(logo_file, 'image')
            if err:
                flash(err, 'danger')
                return redirect(url_for('admin.settings_view'))
            logo_asset = SiteAsset.query.filter_by(asset_key='logo').first()
            if not logo_asset:
                logo_asset = SiteAsset(asset_key='logo')
                db.session.add(logo_asset)
            logo_asset.data = stored['data']
            logo_asset.mime_type = stored['mime_type']
            logo_asset.file_size = stored['file_size']
            logo_asset.original_filename = stored['original_filename']
            logo_asset.checksum = stored['checksum']
            db.session.commit()
            logo_url = url_for('media.serve_site_logo', _external=False)
            setting = SiteSetting.query.filter_by(setting_key='logo_url').first()
            if setting:
                setting.setting_value = logo_url
            else:
                setting = SiteSetting(setting_key='logo_url', setting_value=logo_url)
                db.session.add(setting)
            db.session.commit()
            flash('Settings saved successfully.', 'success')
            return redirect(url_for('admin.settings_view'))
        # Explicit allow-list: only these keys can ever be written from the form,
        # so a crafted POST cannot inject arbitrary site_settings rows.
        allowed_keys = [
            'hero_heading', 'hero_subtext', 'announcement_bar', 'footer_text',
            'primary_accent_color', 'secondary_accent_color',
            'contact_email', 'contact_phone', 'social_links',
            'site_title', 'logo_url', 'currency_manual_rate',
        ]
        for key in allowed_keys:
            value = request.form.get(key, '').strip()
            setting = SiteSetting.query.filter_by(setting_key=key).first()
            if setting:
                setting.setting_value = value
            else:
                setting = SiteSetting(setting_key=key, setting_value=value)
                db.session.add(setting)
        db.session.commit()
        currency_manual_rate = request.form.get('currency_manual_rate', '').strip()
        if currency_manual_rate:
            try:
                rate = float(currency_manual_rate)
                from app.models.currency import Currency
                usd = Currency.query.filter_by(code='USD').first()
                if not usd:
                    usd = Currency(code='USD', symbol='$', exchange_rate_to_inr=rate, is_settlement_enabled=False)
                    db.session.add(usd)
                else:
                    usd.exchange_rate_to_inr = rate
                    usd.last_updated = datetime.utcnow()
                inr = Currency.query.filter_by(code='INR').first()
                if not inr:
                    inr = Currency(code='INR', symbol='₹', exchange_rate_to_inr=1.0, is_settlement_enabled=True)
                    db.session.add(inr)
                db.session.commit()
                flash('Currency rate updated successfully.', 'success')
            except (ValueError, TypeError):
                pass
        flash('Settings saved successfully.', 'success')
        return redirect(url_for('admin.settings_view'))
    # Collapse the key/value table into a dict the template can look up directly.
    settings = {s.setting_key: s.setting_value for s in SiteSetting.query.all()}
    return render_template('admin/settings.html', settings=settings)


# POST /admin/settings/logo - admin only.
# Accepts a logo file upload, stores it as a SiteAsset row, and updates the
# logo_url SiteSetting. Returns JSON.
@admin_bp.route('/settings/logo', methods=['POST'])
@admin_required
def settings_logo_upload():
    file = request.files.get('logo')
    if not file or file.filename == '':
        return jsonify({'success': False, 'error': 'No logo file provided.'}), 400
    from app.utils.media import save_media_to_db
    stored, err = save_media_to_db(file, 'image')
    if err:
        return jsonify({'success': False, 'error': err}), 400
    logo_asset = SiteAsset.query.filter_by(asset_key='logo').first()
    if not logo_asset:
        logo_asset = SiteAsset(asset_key='logo')
        db.session.add(logo_asset)
    logo_asset.data = stored['data']
    logo_asset.mime_type = stored['mime_type']
    logo_asset.file_size = stored['file_size']
    logo_asset.original_filename = stored['original_filename']
    logo_asset.checksum = stored['checksum']
    db.session.commit()
    logo_url = url_for('media.serve_site_logo', _external=False)
    setting = SiteSetting.query.filter_by(setting_key='logo_url').first()
    if setting:
        setting.setting_value = logo_url
    else:
        setting = SiteSetting(setting_key='logo_url', setting_value=logo_url)
        db.session.add(setting)
    db.session.commit()
    return jsonify({'success': True, 'logo_url': logo_url})

# ---- Section: Banners ----
# ---------------------------------------------------------------------------
# Banners
# ---------------------------------------------------------------------------
# Homepage carousel slides. The public template shows active banners whose
# start_date/end_date window contains "now"; image_url is a plain URL here even
# though the table also has BLOB columns for uploaded banner bytes.

# GET /admin/banners - admin only. Full (unpaginated) slide list in display
# order. Renders admin/banners.html.


@admin_bp.route('/banners')
@admin_required
def banners_list():
    banners = Banner.query.order_by(Banner.display_order, Banner.id.desc()).all()
    return render_template('admin/banners.html', banners=banners)


# GET|POST /admin/banners/new - admin only. Creates a carousel slide with its
# optional scheduling window. Redirects to the banner list on success.
@admin_bp.route('/banners/new', methods=['GET', 'POST'])
@admin_required
def banner_new():
    form = BannerForm()
    if form.validate_on_submit():
        # title, link_url and the date window are optional; image_url is required.
        file = request.files.get('image')
        image_url = form.image_url.data
        if file and file.filename != '':
            from app.utils.media import save_media_to_db
            stored, err = save_media_to_db(file, 'image')
            if err:
                flash(err, 'danger')
                return render_template('admin/banner_form.html', form=form, banner=None)
            banner = Banner(
                title=form.title.data,
                link_url=form.link_url.data,
                display_order=form.display_order.data,
                is_active=form.is_active.data,
                start_date=form.start_date.data,
                end_date=form.end_date.data,
                banner_data=stored['data'],
                mime_type=stored['mime_type'],
                file_size=stored['file_size'],
                checksum=stored['checksum'],
            )
            db.session.add(banner)
            db.session.commit()
            banner.image_url = url_for('media.serve_banner', banner_id=banner.id, _external=False)
            db.session.commit()
        else:
            banner = Banner(
                title=form.title.data,
                image_url=image_url,
                link_url=form.link_url.data,
                display_order=form.display_order.data,
                is_active=form.is_active.data,
                start_date=form.start_date.data,
                end_date=form.end_date.data,
            )
            db.session.add(banner)
            db.session.commit()
        flash('Banner created successfully.', 'success')
        return redirect(url_for('admin.banners_list'))
    return render_template('admin/banner_form.html', form=form, banner=None)


# GET|POST /admin/banners/<id>/edit - admin only. Updates slide copy, image,
# link and the active/scheduling flags. Redirects to the banner list.
@admin_bp.route('/banners/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def banner_edit(id):
    banner = Banner.query.get_or_404(id)
    form = BannerForm(obj=banner)
    if form.validate_on_submit():
        file = request.files.get('image')
        if file and file.filename != '':
            from app.utils.media import save_media_to_db
            stored, err = save_media_to_db(file, 'image')
            if err:
                flash(err, 'danger')
                return render_template('admin/banner_form.html', form=form, banner=banner)
            banner.banner_data = stored['data']
            banner.mime_type = stored['mime_type']
            banner.file_size = stored['file_size']

            banner.checksum = stored['checksum']
            banner.image_url = url_for('media.serve_banner', banner_id=banner.id, _external=False)
        else:
            banner.image_url = form.image_url.data
        banner.title = form.title.data
        banner.link_url = form.link_url.data
        banner.display_order = form.display_order.data
        banner.is_active = form.is_active.data
        banner.start_date = form.start_date.data
        banner.end_date = form.end_date.data
        db.session.commit()
        flash('Banner updated successfully.', 'success')
        return redirect(url_for('admin.banners_list'))
    return render_template('admin/banner_form.html', form=form, banner=banner)


# POST /admin/banners/<id>/delete - admin only. Hard delete of a slide.
# Redirects to the banner list.
@admin_bp.route('/banners/<int:id>/delete', methods=['POST'])
@admin_required
def banner_delete(id):
    banner = Banner.query.get_or_404(id)
    db.session.delete(banner)
    db.session.commit()
    flash('Banner deleted successfully.', 'success')
    return redirect(url_for('admin.banners_list'))


# POST /admin/banners/<int:id>/image - admin only.
# Accepts an image file upload, stores it as banner BLOB data, and updates the
# image_url. Returns JSON.
@admin_bp.route('/banners/<int:id>/image', methods=['POST'])
@admin_required
def banner_image_upload(id):
    banner = Banner.query.get_or_404(id)
    file = request.files.get('image')
    if not file or file.filename == '':
        return jsonify({'success': False, 'error': 'No image file provided.'}), 400
    from app.utils.media import save_media_to_db
    stored, err = save_media_to_db(file, 'image')
    if err:
        return jsonify({'success': False, 'error': err}), 400
    banner.banner_data = stored['data']
    banner.mime_type = stored['mime_type']
    banner.file_size = stored['file_size']

    banner.checksum = stored['checksum']
    banner.image_url = url_for('media.serve_banner', banner_id=banner.id, _external=False)
    db.session.commit()
    return jsonify({'success': True, 'image_url': banner.image_url})


# ---- Section: Navigation ----
# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
# Storefront menu management. Items may nest via parent_id, and
# target_url_or_page_slug is either a literal URL or the slug of a CMS Page.

# GET /admin/navigation - admin only. All menu items in display order.
# Renders admin/navigation.html.
@admin_bp.route('/navigation')
@admin_required
def navigation_list():
    nav_items = NavigationMenu.query.order_by(NavigationMenu.display_order).all()
    return render_template('admin/navigation.html', nav_items=nav_items)


# POST /admin/navigation/save - admin only. Combined endpoint: if an 'ids' field
# is present it persists the submitted drag order, and if 'label' +
# 'target_url_or_page_slug' are present it appends a new item. Always redirects
# to the navigation list.
@admin_bp.route('/navigation/save', methods=['POST'])
@admin_required
def navigation_save():
    # Branch 1 - reorder. The list page posts the new sequence as a comma
    # separated string of existing ids; non-numeric fragments are ignored.
    ids_str = request.form.get('ids', '')
    if ids_str:
        ids = [int(x.strip()) for x in ids_str.split(',') if x.strip().isdigit()]
        for index, nav_id in enumerate(ids):
            item = NavigationMenu.query.get(nav_id)
            if item:
                item.display_order = index
        db.session.commit()
        flash('Navigation order saved successfully.', 'success')
    # Branch 2 - create. Read straight from request.form (NavigationItemForm is
    # defined but not used by this handler) so the endpoint stays lenient.
    label = request.form.get('label', '').strip()
    target_url_or_page_slug = request.form.get('target_url_or_page_slug', '').strip()
    parent_id = request.form.get('parent_id', '').strip()
    display_order = request.form.get('display_order', 0, type=int)
    # Unchecked checkboxes are simply absent from the form payload.
    is_active = True if request.form.get('is_active') else False
    # Both fields are mandatory for a menu item; otherwise the request is
    # treated as a reorder-only submit and nothing is added.
    if label and target_url_or_page_slug:
        item = NavigationMenu(
            label=label,
            target_url_or_page_slug=target_url_or_page_slug,
            parent_id=int(parent_id) if parent_id else None,
            display_order=display_order,
            is_active=is_active,
        )
        db.session.add(item)
        db.session.commit()
        flash('Navigation item added successfully.', 'success')
    return redirect(url_for('admin.navigation_list'))


# POST /admin/navigation/<id>/delete - admin only. Removes a menu entry. Note
# child items are not re-parented or cascaded explicitly here. Redirects to the
# navigation list.
@admin_bp.route('/navigation/<int:id>/delete', methods=['POST'])
@admin_required
def navigation_delete(id):
    item = NavigationMenu.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    flash('Navigation item deleted successfully.', 'success')
    return redirect(url_for('admin.navigation_list'))

# ---- Section: Customers ----
# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
# Read-only customer directory. Staff accounts are filtered out and no customer
# field (email, password hash, addresses) is editable from this panel.

# GET /admin/customers - admin only. Paginated (20/page) list of accounts with
# role='customer', newest registrations first. Renders admin/customers.html.


@admin_bp.route('/customers')
@admin_required
def customers_list():
    page = request.args.get('page', 1, type=int)
    # role filter keeps other admin/staff accounts out of the customer report.
    customers = User.query.filter_by(role='customer').order_by(User.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/customers.html', customers=customers.items, pagination=customers)


# GET /admin/customers/<id> - admin only. Customer profile plus their full order
# history (newest first). Renders admin/customer_detail.html.
@admin_bp.route('/customers/<int:id>')
@admin_required
def customer_detail(id):
    customer = User.query.get_or_404(id)
    # No role check on the id itself - any user id can be opened here, including
    # another admin's account.
    orders = Order.query.filter_by(user_id=customer.id).order_by(Order.placed_at.desc()).all()
    return render_template('admin/customer_detail.html', customer=customer, orders=orders)

# ---- Section: Reviews ----
# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
# Product review moderation. Reviews are created unapproved by the storefront
# and only surface publicly once is_approved is set here.

# GET /admin/reviews - admin only. Unpaginated moderation queue, newest first.
# Renders admin/reviews.html.


@admin_bp.route('/reviews')
@admin_required
def reviews_list():
    reviews = Review.query.order_by(Review.created_at.desc()).all()
    return render_template('admin/reviews.html', reviews=reviews)


# POST /admin/reviews/<id>/approve - admin only. Publishes a review so it
# appears on the product page. Redirects to the review queue.
@admin_bp.route('/reviews/<int:id>/approve', methods=['POST'])
@admin_required
def review_approve(id):
    review = Review.query.get_or_404(id)
    review.is_approved = True
    db.session.commit()
    flash('Review approved successfully.', 'success')
    return redirect(url_for('admin.reviews_list'))


# POST /admin/reviews/<id>/reject - admin only. "Reject" is implemented as a hard
# delete rather than a hidden flag. Redirects to the review queue.
@admin_bp.route('/reviews/<int:id>/reject', methods=['POST'])
@admin_required
def review_reject(id):
    review = Review.query.get_or_404(id)
    db.session.delete(review)
    db.session.commit()
    flash('Review rejected and removed.', 'success')
    return redirect(url_for('admin.reviews_list'))

# ---- Section: Media Manager (cross-product) ----
# ---------------------------------------------------------------------------
# Media Manager
# ---------------------------------------------------------------------------
# Site-wide asset browser: lists every ProductMedia row across the catalogue for
# auditing, with the same optional filters the per-product uploader uses. This
# view is read-only; uploads happen from the product editor.

# GET /admin/media - admin only. Read-only asset browser. Optional query params:
# '?product_id=' restrict to one product, '?type=image|video' filter by kind,
# '?q=' matches the original filename. Renders admin/media_manager.html.


@admin_bp.route('/media')
@admin_required
def media_manager():
    product_id = request.args.get('product_id', '', type=str)
    media_type = request.args.get('type', '', type=str)
    q = request.args.get('q', '', type=str)
    # The filter sidebar is populated with the full product list for the dropdown.
    products = Product.query.order_by(Product.name).all()
    query = ProductMedia.query
    # Each filter is applied only when present; an empty param means "all".
    if product_id and product_id.isdigit():
        query = query.filter_by(product_id=int(product_id))
    if media_type in ('image', 'video'):
        query = query.filter_by(media_type=media_type)
    if q:
        query = query.filter(ProductMedia.original_filename.ilike(f'%{q}%'))
    # Descending display_order surfaces the most recently uploaded/reordered
    # assets first in the audit view.
    media = query.order_by(ProductMedia.display_order.desc()).all()
    return render_template('admin/media_manager.html', media=media, products=products, filter_product_id=product_id, filter_type=media_type)
