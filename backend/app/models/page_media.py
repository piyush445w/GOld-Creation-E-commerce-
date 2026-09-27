"""Media assets for CMS pages.

PageMedia rows store uploaded images/videos for a Page, similar to
ProductMedia and CategoryMedia. The storefront can read the primary
image URL from the related Page row when rendering a CMS page.
"""
from datetime import datetime

from app import db


class PageMedia(db.Model):
    __tablename__ = 'page_media'

    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey('pages.id'), nullable=False)
    media_type = db.Column(db.String(50), default='image')
    media_url = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100))
    display_order = db.Column(db.Integer, default=0)
    is_primary = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    media_data = db.Column(db.LargeBinary(length=(2 ** 32) - 1))
    file_size = db.Column(db.BigInteger)
    original_filename = db.Column(db.String(255))
    checksum = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
