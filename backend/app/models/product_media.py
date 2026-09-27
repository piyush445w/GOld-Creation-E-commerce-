"""Image/video attachments for a product gallery.

Each row is one gallery asset. Assets can live on disk (media_url) or inline in
the database (media_data), which supports both cloud-hosted and self-contained
installations; checksum and file_size support de-duplication and caching.
Product.primary_image reads this table to pick a card thumbnail.
"""

from app import db
from datetime import datetime


# A single gallery asset (photo or video clip) belonging to a product.
class ProductMedia(db.Model):
    # Singular table name, consistent with the existing schema and migrations.
    __tablename__ = 'product_media'

    id = db.Column(db.Integer, primary_key=True)
    # Owning product; deleting the product removes its gallery entries.
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    # Asset kind - constrained below to 'image' or 'video'.
    media_type = db.Column(db.String(10), nullable=False)
    # Primary asset location when stored externally.
    media_url = db.Column(db.String(255), nullable=False)
    # Optional smaller derivative used in listing grids for faster page loads.
    thumbnail_url = db.Column(db.String(255))
    # MIME type of the uploaded asset, used to set the correct Content-Type.
    mime_type = db.Column(db.String(50))
    # Sort key within the gallery; lower numbers appear earlier in the carousel.
    display_order = db.Column(db.Integer, default=0)
    # Marks the default gallery image; Product.primary_image prefers this row.
    is_primary = db.Column(db.Boolean, default=False)
    # Soft flag to hide an asset without deleting the upload.
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Inline BLOB alternative to media_url for self-contained deployments.
    media_data = db.Column(db.LargeBinary(length=(2**32)-1))
    # Inline BLOB for the thumbnail, used when thumbnail_url is absent.
    thumbnail_data = db.Column(db.LargeBinary(length=(2**32)-1))
    # Uploaded byte size, surfaced in the admin media manager.
    file_size = db.Column(db.BigInteger)
    # Client-side filename, kept for admin reference and download naming.
    original_filename = db.Column(db.String(255))
    # Content hash used to detect duplicate uploads across products.
    checksum = db.Column(db.String(64))

    # Table-level constraint: media_type is restricted to the two supported kinds.
    __table_args__ = (
        db.CheckConstraint(media_type.in_(['image', 'video']), name='ck_product_media_type'),
    )