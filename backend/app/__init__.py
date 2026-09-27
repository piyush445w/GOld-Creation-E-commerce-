"""Application factory and shared Flask extension instances.

This is the composition root of the Gold Creation platform. It wires together
every infrastructure concern the rest of the codebase depends on:

* filesystem paths that let the Flask app serve Jinja2 templates and static
  assets that physically live in the sibling ``frontend/`` directory,
* the extension singletons (``db``, ``login_manager``, ``limiter``, ``mail``,
  ``migrate``) which are created here and later bound to a concrete app,
* ``create_app()`` - the factory that every entry point (``run.py``,
  ``gunicorn.conf.py``, ``seed.py``, the test suite) calls to obtain a
  configured application instance for a given environment.

``app/`` is the Python package; ``backend/`` holds the entry points and the
``frontend/`` directory holds all presentation assets.
"""

from flask import Flask, request, session, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from .config import config
import os

# Absolute path of ``backend/`` - the directory that holds run.py, seed.py,
# migrations/ and tests/. Used to anchor all other relative paths below.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Absolute path of the repository root, i.e. the parent of ``backend/``. The
# frontend/ package of templates and static assets is resolved from here.
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

# ---- Extension singletons -----------------------------------------------------
# These are instantiated without an app so that models, blueprints and utils can
# import them (``from app import db``) at module-import time without creating a
# circular dependency on the factory. They are bound to a real app inside
# create_app() via the *_init_app() calls below.
db = SQLAlchemy()          # ORM session + declarative base for all models in app/models/
login_manager = LoginManager()  # Flask-Login session handling for customer and admin accounts
limiter = Limiter(get_remote_address)  # Request rate limiting keyed on client IP
mail = Mail()              # Transactional email (order confirmations, password resets)
migrate = Migrate()        # Alembic schema migration runner

# Unauthenticated requests to @login_required views are redirected here, and the
# resulting flash message is rendered in the "info" style used by base.html.
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    """Rehydrate the logged-in principal from the ID stored in the session cookie.

    Flask-Login persists only the primary key in the session and calls this
    callback on every request to rebuild the user object, so downstream code can
    rely on ``current_user``, ``current_user.is_admin`` and role checks.
    The int() cast is required because the session stores the key as a string.
    """
    # Imported lazily: app.models imports db from this module, so a top-level
    # import here would form a circular import during package initialisation.
    from app.models.user import User
    return User.query.get(int(user_id))


def create_app(config_name='default'):
    """Build and return a fully configured Flask application.

    This factory is the single place where an app instance is assembled, so
    the dev server, gunicorn workers, seeding scripts and the test suite all
    get an identically wired application. ``config_name`` selects the
    environment-specific settings object from ``app.config.config``.

    The steps below run in a deliberate order: paths and settings first, then
    template globals, then extension binding, then blueprint registration,
    then app-wide hooks and error handlers.
    """
    # Point Flask at the presentation layer. The project keeps backend code and
    # frontend assets in separate top-level folders, so the template and static
    # roots must be pointed outside of backend/app/.
    app = Flask(__name__,
                template_folder=os.path.join(PROJECT_ROOT, 'frontend', 'templates'),
                static_folder=os.path.join(PROJECT_ROOT, 'frontend', 'static'))

    # Copy the class attributes of the selected config onto app.config, then let
    # the config class validate/augment the live app (ProductionConfig and
    # TestingConfig raise here if required environment variables are missing).
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    # Enable the `{% do %}` statement in templates, used by templates that need
    # side effects while rendering (e.g. appending to a list inside a loop).
    app.jinja_env.add_extension('jinja2.ext.do')

    @app.context_processor
    def inject_globals():
        """Expose shopper-facing values to every rendered template.

        Registered as a context processor, so the returned mapping is merged
        into the Jinja context of every render. This is what allows base.html
        to show a live cart/wishlist badge, a currency switcher and a CSRF
        token function without any view having to pass them explicitly.
        """
        from datetime import datetime
        from app.utils.currency_utils import get_visitor_currency
        from app.models.cart import CartItem
        from app.models.currency import Currency
        from app.models.wishlist import WishlistItem
        from flask_login import current_user
        from flask_wtf.csrf import generate_csrf
        from app.models.navigation_menu import NavigationMenu
        from app.models.category import Category
        from app.models.site_setting import SiteSetting

        # Resolve the display currency from the session/cookie/Accept-Language
        # so every price on the page is rendered in the visitor's currency.
        currency = get_visitor_currency(request)
        cart_count = 0
        wishlist_count = 0

        # Badge counts differ by identity: signed-in shoppers read their counts
        # from the database...
        if current_user.is_authenticated:
            cart_count = CartItem.query.filter_by(user_id=current_user.id).count()
            wishlist_count = WishlistItem.query.filter_by(user_id=current_user.id).count()
        else:
            # ...while guests read them from their server-side session. The cart
            # is keyed by a generated guest_session_id, but the guest wishlist is
            # kept as a plain list in the cookie session and merged into a
            # WishlistItem set on login.
            gid = session.get('guest_session_id')
            if gid:
                cart_count = CartItem.query.filter_by(guest_session_id=gid).count()
            wishlist_count = len(session.get('guest_wishlist', []))

        # Only the two supported currencies (INR base, USD converted) appear in
        # the switcher; ordering keeps the rendered markup stable.
        all_currencies = Currency.query.filter(Currency.code.in_(['INR', 'USD'])).order_by(Currency.code).all()

        top_nav_items = NavigationMenu.query.filter_by(parent_id=None, is_active=True).order_by(NavigationMenu.display_order).all()

        footer_categories = Category.query.filter_by(is_active=True, parent_id=None).order_by(Category.display_order).limit(5).all()

        social_links_raw = SiteSetting.query.filter_by(setting_key='social_links').first()
        social_links = []
        if social_links_raw and social_links_raw.setting_value:
            import json
            try:
                social_links = json.loads(social_links_raw.setting_value)
            except Exception:
                social_links = []

        settings = {s.setting_key: s.setting_value for s in SiteSetting.query.all()}

        # `now` is exposed as a callable so templates can format the current
        # time via `now().strftime(...)` rather than freezing it at render setup.
        return dict(current_currency=currency, cart_count=cart_count, wishlist_count=wishlist_count,
                    now=datetime.now, csrf_token=generate_csrf, all_currencies=all_currencies,
                    nav_items=top_nav_items, footer_categories=footer_categories,
                    social_links=social_links, settings=settings)

    # Bind the extension singletons declared above to this app instance.
    # Flask-Migrate additionally receives `db` so `flask db ...` can compare
    # models against the live schema.
    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)

    # Blueprints are imported here, not at module scope, so that every model and
    # utility they reference is already registered on `db` above.
    from app.routes.storefront import storefront_bp
    from app.routes.admin import admin_bp
    from app.routes.auth import auth_bp
    from app.routes.cart_routes import cart_bp
    from app.routes.wishlist_routes import wishlist_bp
    from app.routes.checkout import checkout_bp
    from app.routes.api import api_bp
    from app.routes.media_routes import media_bp

    # URL map layout of the platform:
    #   storefront / cart / wishlist / checkout / media -> root-level shopper URLs
    #   /admin   -> back-office CRUD                  /auth -> session lifecycle
    #   /api     -> JSON endpoints consumed by main.js via fetch()
    app.register_blueprint(storefront_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(cart_bp)
    app.register_blueprint(wishlist_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(media_bp)

    # Import the models package so SQLAlchemy registers every table on the
    # metadata before migrations or create_all() inspect it.
    from app import models  # noqa: F401
    # Register custom Jinja filters/globals (price formatting, media URL
    # building, stock helpers) so templates can call them by bare name.
    from app.utils.templating import register_template_helpers
    register_template_helpers(app)

    @app.route('/health')
    def health_check():
        """Container/orchestrator liveness probe.

        Deliberately does not touch the database so a transient DB outage is
        distinguishable from a dead web process during load balancing.
        """
        return jsonify({'status': 'ok'}), 200

    @app.after_request
    def inject_security_headers(response):
        """Apply the configured hardening headers to every outgoing response.

        Runs on the way out for all routes (including error pages). setdefault
        is used so a view that already set a stricter header keeps its own value.
        """
        headers = app.config.get('SECURITY_HEADERS', {})
        for header, value in headers.items():
            response.headers.setdefault(header, value)
        return response

    @app.errorhandler(404)
    def not_found_error(error):
        """Render the branded storefront 404 page for any unmatched URL."""
        return render_template('storefront/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Roll back the poisoned session/transaction, then show a generic 500.

        Rolling back is essential: without it the failed transaction would be
        left attached to the scoped session and every later request on the same
        worker would fail too.
        """
        db.session.rollback()
        return render_template('storefront/500.html'), 500

    return app
