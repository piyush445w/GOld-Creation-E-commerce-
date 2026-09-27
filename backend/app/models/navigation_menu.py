"""Header/footer navigation entries managed from the admin panel.

Like Category, this is a self-referencing adjacency list (parent_id) supporting
nested menus. Each entry stores a single target string, which the template
resolves as a real URL or as a CMS page slug.
"""

from app import db


# One clickable menu entry, optionally nested under a parent entry.
class NavigationMenu(db.Model):
    # Singular table name; kept as-is to match the existing schema/migrations.
    __tablename__ = 'navigation_menu'

    id = db.Column(db.Integer, primary_key=True)
    # Text rendered in the nav bar or footer column.
    label = db.Column(db.String(100), nullable=False)
    # Either a literal path/URL, or a Page.slug resolved server-side to /page/<slug>.
    target_url_or_page_slug = db.Column(db.String(255), nullable=False)
    # Sort key within the parent group; lower values appear first.
    display_order = db.Column(db.Integer, default=0)
    # Self FK: NULL marks a top-level menu entry.
    parent_id = db.Column(db.Integer, db.ForeignKey('navigation_menu.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    # remote_side disambiguates parent vs. children on a self-referential relationship.
    parent = db.relationship('NavigationMenu', backref=db.backref('children', lazy='dynamic'), remote_side=[id])
