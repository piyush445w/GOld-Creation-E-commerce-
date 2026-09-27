"""
Route blueprints for the Gold Creation storefront.

This package holds the individual Flask blueprints - public storefront, auth,
admin back office, media serving - that are registered on the app in
``app/__init__.py``. Importing a blueprint here keeps the registration code
centralised; the modules themselves stay self-contained (each declares its own
``Blueprint`` and its own access-control decorators such as ``admin_required``).

Note: this file intentionally contains no blueprint registrations. Modules are
imported directly by the app factory.
"""
