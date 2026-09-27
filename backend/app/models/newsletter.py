"""Newsletter mailing-list signups.

A minimal, deliberately decoupled model: the storefront signup form writes a
row here, and admin/export or campaign tooling reads the addresses out. The
unique email keeps repeat submissions idempotent.
"""

from app import db
from datetime import datetime


# A single marketing email subscription.
class NewsletterSubscriber(db.Model):
    __tablename__ = 'newsletter_subscribers'

    id = db.Column(db.Integer, primary_key=True)
    # Unique subscriber address; duplicates are rejected/merged by the signup route.
    email = db.Column(db.String(255), nullable=False, unique=True)
    # Opt-in timestamp, used for consent records and list growth reporting.
    subscribed_at = db.Column(db.DateTime, default=datetime.utcnow)
