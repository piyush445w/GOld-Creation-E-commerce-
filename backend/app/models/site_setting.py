"""Generic key/value store for admin-editable site configuration.

Rather than adding a column per option (shipping thresholds, gateway keys,
support contacts, feature flags), settings are stored as unique key/value rows
that the app reads on demand. The single text value column keeps the schema
stable while the admin panel can add settings without a migration.
"""

from app import db


# One configuration option, addressed by its unique key.
class SiteSetting(db.Model):
    __tablename__ = 'site_settings'

    id = db.Column(db.Integer, primary_key=True)
    # Unique option name (e.g. "free_shipping_threshold"); the lookup key.
    setting_key = db.Column(db.String(100), unique=True, nullable=False)
    # Option value as text; callers parse it (int/float/JSON) as needed.
    setting_value = db.Column(db.Text)
