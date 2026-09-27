# -*- coding: utf-8 -*-
# =============================================================================
# api.py - read-only JSON API blueprint (mounted at /api)
# -----------------------------------------------------------------------------
# Exposes the public catalogue (products, categories) as JSON so external
# clients and integrations can consume store data without scraping the
# server-rendered HTML storefront.
# Every endpoint here is public and read-only; all writes happen in the admin
# blueprint. SQLAlchemy models are never returned directly - each is flattened
# through a *_to_dict serialiser that controls exactly which fields leave the
# system (no internal flags, BLOB media, or admin-only columns).
# =============================================================================

from flask import Blueprint, jsonify, request
from sqlalchemy import or_
from app.models.product import Product
from app.models.category import Category

api_bp = Blueprint('api', __name__)


# ---- Serialisers: define the public JSON shape of each resource ---------------

def product_to_dict(product):
    """Flatten a Product row into its public JSON representation.

    `float()` is used on the Decimal price so jsonify emits a JSON number
    rather than a string, and created_at is ISO-8601 encoded (or null).
    Media and variants are deliberately omitted; clients fetch those separately.
    """
    return {
        'id': product.id,
        'name': product.name,
        'slug': product.slug,
        'description': product.description,
        'base_price': float(product.base_price),
        'sku': product.sku,
        'is_active': product.is_active,
        'category_id': product.category_id,
        'created_at': product.created_at.isoformat() if product.created_at else None,
    }


def category_to_dict(category):
    """Flatten a Category row into its public JSON representation."""
    return {
        'id': category.id,
        'name': category.name,
        'slug': category.slug,
        'description': category.description,
        'is_active': category.is_active,
        'created_at': category.created_at.isoformat() if category.created_at else None,
    }


# ---- Endpoints ---------------------------------------------------------------

@api_bp.after_request
def add_cors_headers(response):
    """Permit cross-origin reads of the API on every response.

    Registered on the blueprint rather than the app because only /api is meant
    to be publicly callable from a browser on another origin.
    """
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response


# GET /api/products - public. Paginated, filterable, searchable catalogue feed.
# Supports ?page= &per_page= &category_slug= &festival= &q= &sort=, and always
# restricts results to active products so drafts/disabled items stay private.
@api_bp.route('/products')
def api_products():
    # Read paging/sort/filter parameters from the query string.
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    category_slug = request.args.get('category_slug')
    festival = request.args.get('festival')
    sort = request.args.get('sort', 'newest')
    q = request.args.get('q', '').strip()

    # Baseline: only products the storefront is allowed to show.
    query = Product.query.filter_by(is_active=True)
    # Narrow to a category by its public slug. An unknown slug is ignored rather
    # than erroring, so a stale link degrades to the full listing.
    if category_slug:
        category = Category.query.filter_by(slug=category_slug, is_active=True).first()
        if category:
            query = query.filter_by(category_id=category.id)
    # `festival=true` selects seasonal/festival-tagged items for themed campaigns.
    if festival == 'true':
        query = query.filter(Product.festival_tag.isnot(None))
    # Free-text search across the fields a shopper would actually type.
    if q:
        search = '%' + q + '%'
        query = query.filter(
            or_(
                Product.name.like(search),
                Product.description.like(search),
                Product.sku.like(search)
            )
        )
    # Sort by price ascending/descending, defaulting to newest first.
    if sort == 'price_low':
        query = query.order_by(Product.base_price.asc())
    elif sort == 'price_high':
        query = query.order_by(Product.base_price.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    # error_out=False returns an empty page instead of a 404 past the last page.
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'products': [product_to_dict(p) for p in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page
    })


# GET /api/product/<slug> - public. Single active product by its public slug;
# a missing or inactive product yields a 404 rather than a null body.
@api_bp.route('/product/<slug>')
def api_product_detail(slug):
    product = Product.query.filter_by(slug=slug, is_active=True).first_or_404()
    return jsonify({'product': product_to_dict(product)})


# GET /api/categories - public. All active categories, used by clients to build
# their own navigation without re-implementing the taxonomy rules.
@api_bp.route('/categories')
def api_categories():
    categories = Category.query.filter_by(is_active=True).all()
    return jsonify({'categories': [category_to_dict(c) for c in categories]})
