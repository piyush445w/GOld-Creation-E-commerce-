"""Image/video attachments for a category gallery.

Each row is one gallery asset. Assets can live on disk (media_url) or inline in
the database (media_data), which supports both cloud-hosted and self-contained
installations; checksum and file_size support de-duplication and caching.
"""

from app import db
from datetime import datetime


class CategoryMedia(db.Model):
    __tablename__ = 'category_media'

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    media_type = db.Column(db.String(10), nullable=False)
    media_url = db.Column(db.String(255), nullable=False)
    thumbnail_url = db.Column(db.String(255))
    mime_type = db.Column(db.String(50))
    display_order = db.Column(db.Integer, default=0)
    is_primary = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    media_data = db.Column(db.LargeBinary(length=(2 ** 32) - 1))
    thumbnail_data = db.Column(db.LargeBinary(length=(2 ** 32) - 1))
    file_size = db.Column(db.BigInteger)
    original_filename = db.Column(db.String(255))
    checksum = db.Column(db.String(64))

    __table_args__ = (
        db.CheckConstraint(media_type.in_(['image', 'video']), name='ck_category_media_type'),
    )

    category = db.relationship('Category', backref=db.backref('media', lazy='dynamic'))
