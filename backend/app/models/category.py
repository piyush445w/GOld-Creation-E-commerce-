"""Product taxonomy, stored as an adjacency list.

Category rows point at their own table through parent_id, giving an arbitrarily
deep tree (e.g. Women > Sarees > Silk Sarees) that the storefront menu and
filter sidebar traverse. Products and category-scoped coupons hang off this
table, and a festival flag lets seasonal collections be surfaced separately.
"""

from app import db
from datetime import datetime


# A node in the catalogue's category tree (parent_id NULL = top-level).
class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    # Human-readable name shown in navigation and breadcrumbs.
    name = db.Column(db.String(100), nullable=False)
    # URL-safe unique key used to build /category/<slug> storefront links.
    slug = db.Column(db.String(100), unique=True, nullable=False)
    # Self-referencing FK: NULL means this is a root category.
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    description = db.Column(db.Text)
    # Optional banner/thumbnail for category landing pages.
    image_url = db.Column(db.String(255))
    # Marks the category as a festival/seasonal collection (Diwali, wedding, etc.).
    is_festival_collection = db.Column(db.Boolean, default=False)
    # Sort key for menu and listing ordering; lower comes first.
    display_order = db.Column(db.Integer, default=0)
    # Soft visibility flag; inactive categories drop out of the storefront.
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Products assigned directly to this category (lazy='dynamic' -> queryable set,
    # so listings filter/count in SQL rather than loading every product).
    products = db.relationship('Product', backref='category', lazy='dynamic')
    # Children of this node; remote_side resolves the self-referential direction.
    subcategories = db.relationship('Category', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')

    @property
    # Counts products in this category only (not subcategories) for admin/UI badges.
    def product_count(self):
        # Local import avoids a circular import with app.models.product.
        from app.models.product import Product
        return Product.query.filter_by(category_id=self.id).count()
