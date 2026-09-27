"""Registered customer / staff accounts.

User is the identity root of the schema: it plugs into Flask-Login via
UserMixin, stores a password hash (never a plaintext password), and owns
addresses, orders, reviews, cart lines, and wishlist lines. It also carries
authentication-support fields - password-reset tokens with expiry, an optional
role for admin authorization, and TOTP 2FA secrets - plus the preferred display
currency used to price the storefront.
"""

from app import db
from datetime import datetime
# UserMixin supplies Flask-Login's id/get_id/is_authenticated and the
# get_id() hook the login manager uses to load a user from a session cookie.
from flask_login import UserMixin


# A customer or staff account; UserMixin makes it a valid Flask-Login user.
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    # Customer display name, used in greetings, reviews, and order history.
    name = db.Column(db.String(100), nullable=False)
    # Unique login identifier; also the newsletter and review contact address.
    email = db.Column(db.String(120), unique=True, nullable=False)
    # Hashed password (e.g. Werkzeug pbkdf2/scrypt); the raw password is never stored.
    password_hash = db.Column(db.String(128), nullable=False)
    # Optional contact number for delivery coordination and OTP flows.
    phone = db.Column(db.String(20))
    # ISO country code; helps pre-select currency and shipping defaults.
    country = db.Column(db.String(2))
    # Currency the storefront should display prices in for this user.
    preferred_currency = db.Column(db.String(3), default='INR')
    # Password-reset token, unique when present so a lookup finds one user.
    reset_token = db.Column(db.String(100), nullable=True, unique=True)
    # Expiry for reset_token; checked to reject stale or reused reset links.
    reset_token_expires_at = db.Column(db.DateTime, nullable=True)
    # Authorization level (e.g. "customer", "admin"); checked by admin routes.
    role = db.Column(db.String(20), default='customer')
    # Shared secret for TOTP 2FA; only meaningful when totp_enabled is True.
    totp_secret = db.Column(db.String(32), nullable=True)
    # Whether 2FA is currently required after password login.
    totp_enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # All lazy='dynamic': per-user collections are queried/filtered in SQL
    # (e.g. paginated order history), not eagerly loaded on every access.
    # Saved address book; the user picks one of these at checkout.
    addresses = db.relationship('Address', backref='user', lazy='dynamic')
    # Order history; nullable user_id on Order allows guest orders to coexist.
    orders = db.relationship('Order', backref='user', lazy='dynamic')
    # Reviews written by this customer (shown in the admin moderation queue).
    reviews = db.relationship('Review', backref='user', lazy='dynamic')
    # Cart lines owned by this account; guest carts are merged in on sign-in.
    cart_items = db.relationship('CartItem', backref='user', lazy='dynamic')
    # Saved-for-later products for this account.
    wishlist_items = db.relationship('WishlistItem', backref='user', lazy='dynamic')
