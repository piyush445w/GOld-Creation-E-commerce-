"""Customer product reviews and ratings.

A Review is one customer's rating/comment for one product, enforced unique per
(product, user) so re-submitting updates the existing row. Rows start
unapproved and only appear publicly after moderation; the properties at the
bottom provide null-safe display strings for the admin review queue.
"""

from app import db
from datetime import datetime


# A single customer rating + comment attached to a product.
class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    # Reviewed product; the product detail page aggregates these ratings.
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    # Reviewing customer; required, so reviews are attributable and unique per user.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Star rating as an integer; the admin UI and templates render it as stars.
    rating = db.Column(db.Integer, nullable=False)
    # Optional free-text comment.
    comment = db.Column(db.Text)
    # Moderation flag: defaults to False so new reviews stay hidden until approved.
    is_approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # One review per customer per product; a resubmission updates the same row.
    __table_args__ = (
        db.UniqueConstraint('product_id', 'user_id', name='unique_product_user_review'),
    )

    @property
    # Product name for admin listings; None-safe in case the product is deleted.
    def product_name(self):
        return self.product.name if self.product else None

    @property
    # Reviewer display name, shown in the moderation queue; None if the user is gone.
    def customer_name(self):
        return self.user.name if self.user else None

    @property
    # Reviewer email, used by admins to follow up or verify a purchase; None-safe.
    def customer_email(self):
        return self.user.email if self.user else None
