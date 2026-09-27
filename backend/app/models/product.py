"""Sellable catalogue items (sarees, lehengas, home textiles).

Product is the merchandising-level record: slug, SEO copy, base price, and a
festival tag used to group seasonal drops. It owns the concrete purchasable
ProductVariants (size/color + stock), the ProductMedia gallery, customer
Reviews, and WishlistItem references. Pricing shown in listings comes from
base_price or a variant override.
"""

from app import db
from sqlalchemy import Numeric
from datetime import datetime
# Imported directly (not only via relationships) because primary_image queries
# ProductMedia in SQL to pick the gallery image.
from app.models.product_media import ProductMedia


# A catalogue product: descriptive content, base price, and its child records.
class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    # Owning category in the taxonomy; required so every product is browsable.
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    # Display name of the garment or textile product.
    name = db.Column(db.String(200), nullable=False)
    # Unique URL key for the product detail page.
    slug = db.Column(db.String(200), unique=True, nullable=False)
    # Long-form fabric/care/story copy shown on the product page.
    description = db.Column(db.Text)
    # List price in INR, used when a variant has no price_override.
    base_price = db.Column(Numeric(10, 2), nullable=False)
    # Optional parent-level SKU for integrations and catalogue feeds.
    sku = db.Column(db.String(100), unique=True)
    # Soft visibility flag; inactive products are hidden from listings and search.
    is_active = db.Column(db.Boolean, default=True)
    # Optional season label (e.g. "Diwali 2026") for filtering festival drops.
    festival_tag = db.Column(db.String(100))
    # SEO overrides, falling back to name/description when blank.
    meta_title = db.Column(db.String(100))
    meta_description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Refreshed on every save, so stale cache entries can be detected.
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # All lazy='dynamic': collections are queried/filtered in SQL, never fully loaded.
    # Size/color variants that carry their own price and stock levels.
    variants = db.relationship('ProductVariant', backref='product', lazy='dynamic')
    # Image/video gallery rows backing the product page carousel.
    media = db.relationship('ProductMedia', backref='product', lazy='dynamic')
    # Customer reviews, filtered by is_approved for public display.
    reviews = db.relationship('Review', backref='product', lazy='dynamic')
    # Wishlist entries; used to render the "saved" heart state on cards.
    wishlist_items = db.relationship('WishlistItem', backref='product', lazy='dynamic')

    @property
    # Returns the gallery image URL for cards/OG tags: the row flagged primary,
    # else the first active image by display_order, else None when the product
    # has no usable media. Consumed by listing templates and the admin preview.
    def primary_image(self):
        primary = ProductMedia.query.filter_by(product_id=self.id, is_primary=True, is_active=True).first()
        if primary:
            return primary.media_url
        first = ProductMedia.query.filter_by(product_id=self.id, is_active=True).order_by(ProductMedia.display_order).first()
        return first.media_url if first else None
