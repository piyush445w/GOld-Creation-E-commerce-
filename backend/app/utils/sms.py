# -*- coding: utf-8 -*-
# =============================================================================
# sms.py — Twilio SMS & WhatsApp notifications
# -----------------------------------------------------------------------------
# Sends order-status updates to customers over both SMS and WhatsApp via the
# Twilio REST API. Credentials are read from the app config so the module is a
# no-op (rather than a crash) when Twilio is not configured. All network errors
# are swallowed and logged so notifications never block checkout or callbacks.
# =============================================================================
import logging
from twilio.rest import Client
from flask import current_app

logger = logging.getLogger(__name__)


# Send a plain SMS via Twilio; returns False (without raising) when credentials
# are missing or the upstream API call fails.
def send_sms(to, body):
    account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN')
    from_number = current_app.config.get('TWILIO_PHONE_NUMBER')

    if not account_sid or not auth_token or not from_number:
        return False

    try:
        client = Client(account_sid, auth_token)
        client.messages.create(body=body, from_=from_number, to=to)
        return True
    except Exception:
        logger.exception('Failed to send SMS to %s', to)
        return False


# Send a WhatsApp message via Twilio; auto-prefixes the `whatsapp:` scheme to
# both the `to` and `from` numbers when missing.
def send_whatsapp(to, body):
    account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN')
    from_number = current_app.config.get('TWILIO_WHATSAPP_NUMBER')

    if not account_sid or not auth_token or not from_number:
        return False

    if not to.startswith('whatsapp:'):
        to = f'whatsapp:{to}'
    if not from_number.startswith('whatsapp:'):
        from_number = f'whatsapp:{from_number}'

    try:
        client = Client(account_sid, auth_token)
        client.messages.create(body=body, from_=from_number, to=to)
        return True
    except Exception:
        logger.exception('Failed to send WhatsApp message to %s', to)
        return False


# Build and dispatch an order-status notification over both SMS and WhatsApp
# to the order's user (no-op when the user or phone is missing).
def send_order_notification(order, status):
    user = order.user
    if not user:
        return

    phone = user.phone
    if not phone:
        return

    body = f'Your order {order.order_number} status has been updated to: {status}. Total: {order.total} {order.display_currency}'
    send_sms(phone, body)

    if user.phone:
        whatsapp_body = f'Hello {user.name}, your order {order.order_number} is now {status}. Thank you for shopping with us!'
        send_whatsapp(phone, whatsapp_body)
