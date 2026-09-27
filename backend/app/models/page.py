"""CMS content pages (About Us, Privacy Policy, Return Policy, etc.).

Pages are slug-addressed static content blocks authored in the admin panel, with
optional SEO overrides. NavigationMenu entries reference pages by slug, so
editing a page updates the linked footer/header link automatically.
"""

from app import db
from datetime import datetime


# A single editable content page served at /page/<slug>.
class Page(db.Model):
    __tablename__ = 'pages'

    id = db.Column(db.Integer, primary_key=True)
    # Unique URL key; also the value stored in NavigationMenu.target_url_or_page_slug.
    slug = db.Column(db.String(100), unique=True, nullable=False)
    # On-page heading.
    title = db.Column(db.String(100), nullable=False)
    # Body content (HTML/Markdown as entered by the admin).
    content = db.Column(db.Text, nullable=False)
    # SEO overrides; when empty the renderer falls back to the page title.
    meta_title = db.Column(db.String(100))
    meta_description = db.Column(db.String(255))
    # Draft/published switch; unpublished pages return 404 on the storefront.
    is_published = db.Column(db.Boolean, default=False)
    # Set on insert and refreshed on every save, for freshness checks and caching.
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    media = db.relationship('PageMedia', backref='page', lazy='dynamic')
