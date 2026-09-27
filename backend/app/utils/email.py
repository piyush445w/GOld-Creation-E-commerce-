# -*- coding: utf-8 -*-
# =============================================================================
# email.py — Transactional email delivery via Flask-Mail
# -----------------------------------------------------------------------------
# Wraps Flask-Mail so that notification failures (unconfigured SMTP, network
# timeouts) can never propagate out of checkout/auth flows. Provides order
# confirmations, password-reset links and abandoned-cart reminders.
# =============================================================================
import logging
from flask_mail import Message
from app import mail

logger = logging.getLogger(__name__)


# Send an HTML email; swallows any mail-server exception so callers (checkout,
# auth, scheduler) never block on notification delivery.
def send_email(subject, recipient, html_body):
    """Send an email. Never lets a mail-server failure (e.g. unconfigured or
    unreachable SMTP) propagate and break the caller's request — notification
    delivery should never block a checkout, signup, or password reset."""
    try:
        msg = Message(subject=subject, recipients=[recipient], html=html_body)
        mail.send(msg)
        return True
    except Exception:
        logger.exception('Failed to send email to %s', recipient)
        return False


# Fire the post-order confirmation email to the order's user (no-op if the
# order has no associated user, e.g. a legacy guest order).
def send_order_confirmation(order):
    user = order.user
    if not user:
        return
    recipient = user.email
    subject = f'Order Confirmation - {order.order_number}'
    html_body = f'''
    <h2>Thank you for your order!</h2>
    <p>Order Number: {order.order_number}</p>
    <p>Total: {order.total} {order.display_currency}</p>
    <p>Status: {order.status}</p>
    <p>We will notify you when your order is shipped.</p>
    '''
    send_email(subject, recipient, html_body)


# Send the password-reset email containing the single-use reset link.
def send_password_reset_email(user, reset_url):
    recipient = user.email
    subject = 'Password Reset Request'
    html_body = f'''
    <p>Hello {user.name},</p>
    <p>You requested a password reset. Click the link below to reset your password:</p>
    <p><a href="{reset_url}">Reset Password</a></p>
    <p>This link will expire in 1 hour.</p>
    <p>If you did not request this, please ignore this email.</p>
    '''
    send_email(subject, recipient, html_body)


# Send the abandoned-cart reminder listing the user's left-behind line items.
def send_abandoned_cart_email(user, cart_items):
    recipient = user.email
    subject = 'You left items in your cart'
    items_html = ''
    for item in cart_items:
        variant = item.variant
        product = variant.product if variant else None
        name = product.name if product else 'Unknown Product'
        items_html += f'<li>{name} x {item.quantity}</li>'

    html_body = f'''
    <p>Hello {user.name},</p>
    <p>We noticed you left some items in your cart. Complete your order now!</p>
    <ul>{items_html}</ul>
    <p><a href="/cart">View Cart</a></p>
    '''
    send_email(subject, recipient, html_body)
