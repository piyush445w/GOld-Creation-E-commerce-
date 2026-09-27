"""Homepage hero/promo carousel slides.

Banners are pure presentation records: admin-managed images with an optional
click-through link, ordering, an active flag, and a scheduling window. They
have no foreign keys, so the storefront carousel can load them cheaply without
joining into the catalogue.
"""

from app import db
from datetime import datetime


# A single carousel slide shown on the storefront landing page.
class Banner(db.Model):
    __tablename__ = 'banners'

    id = db.Column(db.Integer, primary_key=True)
    # Admin-facing caption; optional because the image alone may be sufficient.
    title = db.Column(db.String(100))
    # URL/path of the image when assets live outside the database.
    image_url = db.Column(db.String(255))
    # Optional target the slide links to (category, page slug, or external URL).
    link_url = db.Column(db.String(255))
    # Lower values render first; ties fall back to insertion order.
    display_order = db.Column(db.Integer, default=0)
    # Soft on/off switch so slides can be retired without deleting history.
    is_active = db.Column(db.Boolean, default=True)
    # Optional scheduling window; when both set, the storefront shows the banner
    # only between start_date and end_date (e.g. Diwali-only campaigns).
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    # Inline BLOB alternative to image_url, for self-contained deployments.
    banner_data = db.Column(db.LargeBinary(length=(2**32)-1))
    # MIME type of banner_data, needed to stream the bytes back to the browser.
    mime_type = db.Column(db.String(100))
    # Size/checksum metadata for cached or de-duplicated uploads.
    file_size = db.Column(db.BigInteger)
    checksum = db.Column(db.String(64))