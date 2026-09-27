"""Alembic migration package for Gold Creation.

Making ``migrations`` a package lets Alembic (via ``flask db ...``, which is
initialised by ``migrate.init_app(app, db)`` in the app factory) discover the
revision chain in ``versions/``. Each revision is a small, ordered schema change
applied on top of its ``down_revision``; the chain is what upgrades a deployed
MySQL database to match the current SQLAlchemy models in ``app/models``.

``env.py`` supplies the runtime context (it hands Alembic the Flask app config
and the shared ``db.metadata``), and ``alembic.ini`` holds the non-Python
migration settings such as the script location and logging configuration.
"""
