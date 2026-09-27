# -*- coding: utf-8 -*-
# =============================================================================
# scheduler.py — APScheduler background jobs for Gold Creation
# -----------------------------------------------------------------------------
# Owns the module-level BackgroundScheduler and the two recurring jobs it runs:
# a daily midnight FX refresh from admin settings (currency_utils.refresh_currency_rates) and a
# 24-hourly abandoned-cart sweep that emails registered users who left items
# behind. start_scheduler() is called once from the app factory.
# =============================================================================
from datetime import datetime, timedelta
from flask import current_app
from apscheduler.schedulers.background import BackgroundScheduler
from app.utils.currency_utils import refresh_currency_rates
from app.utils.email import send_abandoned_cart_email
from app.models.user import User
from app.models.cart import CartItem
from app import db


# Single shared scheduler instance; started by start_scheduler() and stopped at app teardown.
scheduler = BackgroundScheduler()


# Daily job: find CartItems older than 24h that belong to a registered user and
# email each affected user once with the full list of their abandoned items.
def check_abandoned_carts():
    with current_app.app_context():
        threshold = datetime.utcnow() - timedelta(hours=24)
        abandoned_carts = (
            CartItem.query.filter(CartItem.added_at < threshold)
            .filter(CartItem.user_id.isnot(None))
            .all()
        )

        # Group the stale line items by user so each user gets a single email.
        user_carts = {}
        for item in abandoned_carts:
            if item.user_id not in user_carts:
                user_carts[item.user_id] = []
            user_carts[item.user_id].append(item)

        for user_id, items in user_carts.items():
            user = User.query.get(user_id)
            if not user or not user.email:
                continue
            send_abandoned_cart_email(user, items)


# Register and start both jobs; idempotent thanks to replace_existing=True.
def start_scheduler():
    scheduler.add_job(
        func=refresh_currency_rates,
        trigger='cron',
        hour=0,
        minute=0,
        id='refresh_currency_rates',
        replace_existing=True,
    )
    scheduler.add_job(
        func=check_abandoned_carts,
        trigger='interval',
        hours=24,
        id='check_abandoned_carts',
        replace_existing=True,
    )
    scheduler.start()
