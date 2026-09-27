"""Template helpers exposed to every Jinja render."""
from markupsafe import Markup
from flask_wtf.csrf import generate_csrf
from flask import url_for

CSRF_FIELD_NAME = 'csrf_token'


def csrf_input():
    """Render the hidden CSRF field that FlaskForm expects.

    Exposed as a Jinja global rather than a ``{% macro %}`` because macros
    defined in a parent template are not visible to templates that extend it,
    which previously left admin pages raising ``UndefinedError``.
    """
    return Markup('<input type="hidden" name="{}" value="{}">').format(
        CSRF_FIELD_NAME, generate_csrf()
    )


def resolve_nav_url(target_url_or_page_slug):
    """Resolve a NavigationMenu target to an actual URL.

    If the target starts with http://, https://, or /, return as-is.
    Block localhost/loopback URLs so internal development addresses do not
    leak into the public navigation. Otherwise treat it as a Page.slug and
    resolve to /page/<slug>.
    """
    if not target_url_or_page_slug:
        return '#'
    target = target_url_or_page_slug.strip()
    if target.startswith(('http://', 'https://')):
        host_part = target.split('://', 1)[1].split('/', 1)[0].split(':', 1)[0]
        if host_part in ('127.0.0.1', 'localhost', '0.0.0.0', '::1'):
            return '#'
        return target
    if target.startswith('/'):
        return target
    from app.models.page import Page
    page = Page.query.filter_by(slug=target, is_published=True).first()
    if page:
        return url_for('storefront.page', slug=target)
    return '#'


def register_template_helpers(app):
    """Register helpers that must be available in every template."""
    app.jinja_env.globals['csrf_input'] = csrf_input
    app.jinja_env.globals['resolve_nav_url'] = resolve_nav_url
