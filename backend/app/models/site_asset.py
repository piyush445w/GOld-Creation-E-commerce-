"""Site-level media assets such as logos and favicons.

Each row stores a binary asset directly in MySQL as a BLOB, keyed by an
application-defined string (e.g. `'logo'`). This supports self-contained
deployments where static assets are not served from disk or a CDN.
"""

from app import db


class SiteAsset(db.Model):
    """BLOB-backed site asset identified by a string key."""

    __tablename__ = 'site_assets'

    id = db.Column(db.Integer, primary_key=True)
    asset_key = db.Column(db.String(100), unique=True, nullable=False)
    data = db.Column(db.LargeBinary(length=(2 ** 32) - 1))
    mime_type = db.Column(db.String(100))
    file_size = db.Column(db.BigInteger)
    checksum = db.Column(db.String(64))
    original_filename = db.Column(db.String(255))
