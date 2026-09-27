from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Length
import pyotp
import qrcode
import io
import base64
from app.models.user import User
from app import db, login_manager
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
from datetime import datetime, timedelta

from app.utils.email import send_password_reset_email
from app import limiter

# =============================================================================
# Blueprint: auth
# URL Prefix: (none - registered at root: /signup, /login, /logout,
#   /forgot-password, /reset-password/<token>, /admin/login, /admin/2fa-setup,
#   /admin/2fa-verify)
# Role: Identity & session module. Handles customer signup/login/logout, the
#   password-reset email flow, and the admin login path which requires a
#   TOTP 2FA verification step. Also exposes 2FA setup/verify for admins.
# Templates rendered:
#   storefront/signup.html, storefront/login.html, storefront/forgot_password.html,
#   storefront/reset_password.html, admin/login.html, auth/admin_2fa.html
# =============================================================================

auth_bp = Blueprint('auth', __name__)

# In-memory brute-force guard for admin logins, keyed by IP address.
# Holds timestamps of recent attempts so we can cap at 5 per 15 minutes.
_admin_login_attempts = {}


# ---- Section: Password Reset Token Helpers ----
# generate_reset_token stores a single-use URL-safe token on the user record
# with a 1-hour expiry, then commits so the token is queryable by
# verify_reset_token. Returns the token to embed in the reset email.
def generate_reset_token(user):
    token = secrets.token_urlsafe(32)
    user.reset_token = token
    user.reset_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    db.session.commit()
    return token


# verify_reset_token looks up a user by token and ensures it has not expired.
# Returns the User or None (so callers can distinguish "bad token" from
# "no user" without leaking which emails are registered).
def verify_reset_token(token):
    user = User.query.filter_by(reset_token=token).first()
    if user and user.reset_token_expires_at > datetime.utcnow():
        return user
    return None


# ---- Section: WTForms ----
# SignupForm enforces name length, email format, password >= 6 chars, and
# password confirmation equality. Its custom validate_email raises a
# ValidationError to prevent duplicate accounts at the form layer.

class SignupForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

    def validate_email(self, field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError('Email already registered.')


# LoginForm adds a remember_me checkbox; the flag is passed straight to
# flask_login.login_user to control session cookie persistence.

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')


# ForgotPasswordForm only accepts a valid, registered email. Its custom
# validator raises ValidationError to avoid leaking which emails exist,
# but the view still flashes a generic message either way.

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Reset Password')

    def validate_email(self, field):
        user = User.query.filter_by(email=field.data).first()
        if not user:
            raise ValidationError('No account with that email.')


# ResetPasswordForm is used on the token-protected page; it enforces a new
# password and its confirmation but does not validate the token itself.

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')


# AdminLoginForm is the first step of the admin login flow; the 2FA token
# form (Admin2FAForm) is used on the follow-up verify page.

class AdminLoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


# Admin2FAForm requires a 6-digit token for the TOTP verification step.

class Admin2FAForm(FlaskForm):
    token = StringField('Verification Code', validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField('Verify')


# ---- Section: 2FA Setup & Verify (admin only) ----
# Route: GET/POST /admin/2fa-setup  (admin session required)
# Lets an admin enable TOTP 2FA. On POST it persists the session secret
# (stored temporarily in the session) to the user record. On GET it renders
# a QR code the admin scans with an authenticator app.
@auth_bp.route('/admin/2fa-setup', methods=['GET', 'POST'])
def admin_2fa_setup():
    admin_user_id = session.get('admin_user_id')
    if not admin_user_id:
        return 'Not Found', 404
    user = User.query.get(admin_user_id)
    if not user or user.role != 'admin':
        session.pop('admin_user_id', None)
        return 'Not Found', 404
    if request.method == 'POST':
        secret = session.pop('2fa_setup_secret', None)
        if not secret:
            flash('Session expired. Please try again.', 'danger')
            return redirect(url_for('auth.admin_2fa_setup'))
        user.totp_secret = secret
        user.totp_enabled = True
        db.session.commit()
        flash('Two-factor authentication enabled.', 'success')
        return redirect(url_for('admin.dashboard'))
    secret = user.totp_secret or pyotp.random_base32()
    session['2fa_setup_secret'] = secret
    qr = qrcode.make(pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name='Gold Creation'))
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return render_template('auth/admin_2fa.html', setup_mode=True, qr_b64=qr_b64)

# Route: GET/POST /admin/2fa-verify  (public, rate-limited 10/15min)
# Second step of admin login. Reads pending_2fa_user_id from the session
# (set by admin_login when totp_enabled is true) and verifies the 6-digit
# code before establishing an independent admin session.
@auth_bp.route('/admin/2fa-verify', methods=['GET', 'POST'])
@limiter.limit('10 per 15 minutes')
def admin_2fa_verify():
    form = Admin2FAForm()
    pending_user_id = session.get('pending_2fa_user_id')
    if not pending_user_id:
        return redirect(url_for('auth.admin_login'))
    if form.validate_on_submit():
        user = User.query.get(pending_user_id)
        if not user or not user.totp_secret:
            flash('Invalid request.', 'danger')
            return redirect(url_for('auth.admin_login'))
        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(form.token.data):
            session.pop('pending_2fa_user_id', None)
            session['admin_user_id'] = user.id
            flash('Login successful.', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid verification code.', 'danger')
    return render_template('auth/admin_2fa.html', form=form, verify_mode=True)


# ---- Section: Customer Signup / Login / Logout ----
# Route: GET/POST /signup  (public, rate-limited 10/hour)
# Customer registration. Redirects away if already logged in. On success it
# creates the user, logs them in, and merges any guest cart/wishlist into the
# new account so the session is preserved across the upgrade.
@auth_bp.route('/signup', methods=['GET', 'POST'])
@limiter.limit('10 per hour')
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('storefront.index'))
    form = SignupForm()
    if form.validate_on_submit():
        user = User(
            name=form.name.data,
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data),
            role='customer'
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        guest_gid = session.get('guest_session_id')
        if guest_gid:
            from app.models.cart import CartItem
            from app.models.wishlist import WishlistItem
            guest_cart_items = CartItem.query.filter_by(guest_session_id=guest_gid).all()
            for guest_item in guest_cart_items:
                existing = CartItem.query.filter_by(user_id=user.id, product_variant_id=guest_item.product_variant_id).first()
                if existing:
                    existing.quantity += guest_item.quantity
                    db.session.delete(guest_item)
                else:
                    guest_item.user_id = user.id
                    guest_item.guest_session_id = None
            guest_wishlist_items = WishlistItem.query.filter_by(guest_session_id=guest_gid).all()
            for guest_item in guest_wishlist_items:
                existing = WishlistItem.query.filter_by(user_id=user.id, product_id=guest_item.product_id).first()
                if not existing:
                    guest_item.user_id = user.id
                    guest_item.guest_session_id = None
                else:
                    db.session.delete(guest_item)
            db.session.commit()
        flash('Account created successfully.', 'success')
        return redirect(url_for('storefront.index'))
    return render_template('storefront/signup.html', form=form)


# Route: GET/POST /login  (public, rate-limited 10/minute)
# Customer login. Verifies credentials, then merges any guest session cart and
# wishlist into the authenticated account before redirecting (honoring `next`).
@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('storefront.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if not user or not check_password_hash(user.password_hash, form.password.data):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('auth.login'))
        login_user(user, remember=form.remember_me.data)
        from app.models.cart import CartItem
        from app.models.wishlist import WishlistItem
        guest_gid = session.get('guest_session_id')
        if guest_gid:
            guest_cart_items = CartItem.query.filter_by(guest_session_id=guest_gid).all()
            for guest_item in guest_cart_items:
                existing = CartItem.query.filter_by(user_id=user.id, product_variant_id=guest_item.product_variant_id).first()
                if existing:
                    existing.quantity += guest_item.quantity
                    db.session.delete(guest_item)
                else:
                    guest_item.user_id = user.id
                    guest_item.guest_session_id = None
            guest_wishlist_items = WishlistItem.query.filter_by(guest_session_id=guest_gid).all()
            for guest_item in guest_wishlist_items:
                existing = WishlistItem.query.filter_by(user_id=user.id, product_id=guest_item.product_id).first()
                if not existing:
                    guest_item.user_id = user.id
                    guest_item.guest_session_id = None
                else:
                    db.session.delete(guest_item)
            db.session.commit()
        next_page = request.args.get('next')
        return redirect(next_page or url_for('storefront.index'))
    return render_template('storefront/login.html', form=form)


# Route: POST /logout  (login_required)
# Ends the authenticated session and clears the identity cookie.
@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('storefront.index'))


# Route: POST /admin/logout  (admin session required)
# Ends the independent admin session without affecting the customer session.
@auth_bp.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin_user_id', None)
    flash('You have been logged out of the admin panel.', 'info')
    return redirect(url_for('auth.admin_login'))


# ---- Section: Password Reset Flow ----
# Route: GET/POST /forgot-password  (public, rate-limited 5/hour)
# Step 1 of reset. Always flashes a generic success message regardless of
# whether the email exists, to avoid user enumeration. On a valid account it
# generates a 1-hour token and emails the reset link.
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('5 per hour')
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('storefront.index'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            token = generate_reset_token(user)
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            send_password_reset_email(user, reset_url)
        flash('If an account exists with that email, you will receive a reset link.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('storefront/forgot_password.html', form=form)


# Route: GET/POST /reset-password/<token>  (public)
# Step 2 of reset. Validates the token (and its expiry) before rendering the
# form; on submit it hashes the new password, clears the token fields, and
# sends the user back to login.
@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('storefront.index'))
    user = verify_reset_token(token)
    if not user:
        flash('Invalid or expired reset token.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password_hash = generate_password_hash(form.password.data)
        user.reset_token = None
        user.reset_token_expires_at = None
        db.session.commit()
        flash('Password reset successfully. Please log in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('storefront/reset_password.html', form=form)


# ---- Section: Admin Login (with TOTP 2FA) ----
# Route: GET/POST /admin/login  (public, rate-limited 15/15min)
# Admin-only entry point. Uses an independent admin session key (session['admin_user_id'])
# so admin and customer sessions can coexist in the same browser. Enforces a
# 5-attempt-per-15-minutes cap per IP and requires role='admin'. If the admin has
# totp_enabled, the credentials pass and the user id are stashed in the session
# and the flow redirects to /admin/2fa-verify instead of logging in immediately.
@auth_bp.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit('15 per 15 minutes')
def admin_login():
    admin_user_id = session.get('admin_user_id')
    if admin_user_id:
        existing = User.query.get(admin_user_id)
        if existing and existing.role == 'admin':
            return redirect(url_for('admin.dashboard'))
    form = AdminLoginForm()
    if form.validate_on_submit():
        ip = request.remote_addr
        now = datetime.utcnow()
        if ip not in _admin_login_attempts:
            _admin_login_attempts[ip] = []
        _admin_login_attempts[ip].append(now)
        attempts = [t for t in _admin_login_attempts[ip] if now - t < timedelta(minutes=15)]
        _admin_login_attempts[ip] = attempts
        if len(attempts) >= 5:
            flash('Too many login attempts. Please try again later.', 'danger')
            return redirect(url_for('auth.admin_login'))
        user = User.query.filter_by(email=form.email.data).first()
        if not user or not check_password_hash(user.password_hash, form.password.data):
            flash('Invalid credentials.', 'danger')
            return redirect(url_for('auth.admin_login'))
        if user.role != 'admin':
            return 'Not Found', 404
        if user.totp_enabled:
            session['pending_2fa_user_id'] = user.id
            return redirect(url_for('auth.admin_2fa_verify'))
        session['admin_user_id'] = user.id
        _admin_login_attempts.pop(ip, None)
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/login.html', form=form)



