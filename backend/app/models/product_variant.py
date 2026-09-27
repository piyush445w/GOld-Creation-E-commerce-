"""Individually purchasable size/color combinations of a Product.

This is the unit of stock and the unit customers actually buy: a saree in "Free
Size / Maroon" is one variant. CartItem and OrderItem both reference variants,
so inventory decrements and purchase history are tracked at this granularity.
"""

from app import db
from sqlalchemy import Numeric
from datetime import datetime


# One size/color SKU-level variant of a product, with its own price and stock.
class ProductVariant(db.Model):
    __tablename__ = 'product_variants'

    id = db.Column(db.Integer, primary_key=True)
    # Parent product; determines the listing page, description, and base price.
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    # Apparel size label (e.g. "Free Size", "XL") for ethnic wear and textiles.
    size = db.Column(db.String(20))
    # Colorway name shown as a swatch on the product page.
    color = db.Column(db.String(50))
    # Variant-level SKU for inventory feeds and integrations.
    sku = db.Column(db.String(100))
    # Price for this variant; when NULL the app falls back to Product.base_price.
    price_override = db.Column(Numeric(10, 2), nullable=True)
    # Units on hand; checked before checkout and decremented when an order is placed.
    stock_quantity = db.Column(db.Integer, default=0)
    # Optional variant-specific image (e.g. a different colorway photo).
    image_url = db.Column(db.String(255))
    # Inline BLOB alternative to image_url, with its own MIME type for serving.
    variant_image_data = db.Column(db.LargeBinary(length=(2**32)-1))
    variant_image_mime = db.Column(db.String(100))

    # Cart lines for this variant; used to show "X in cart" and merge duplicates.
    cart_items = db.relationship('CartItem', backref='variant', lazy='dynamic')
    # Purchased history for this variant; drives variant sales stats and restock hints.
    order_items = db.relationship('OrderItem', backref='variant', lazy='dynamic')