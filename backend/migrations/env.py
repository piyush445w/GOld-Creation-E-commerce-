# -*- coding: utf-8 -*-
# =============================================================================
# migrations/env.py — Alembic migration runner for the Flask-SQLAlchemy app
# -----------------------------------------------------------------------------
# Configures Alembic to use the app's SQLAlchemy metadata as the autogenerate
# target. In online mode it pulls the DB URL from the Flask app config so the
# same connection string used by the app is used for migrations; in offline
# mode (`alembic upgrade head --sql`) it reads the URL from alembic.ini.
# =============================================================================
from __future__ import with_statement
import sys
import os
from logging.config import fileConfig

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

fileConfig(config.config_file_name)

from app import db
target_db = db

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    try:
        from flask import current_app
        db_url = current_app.config.get('SQLALCHEMY_DATABASE_URI')
        if db_url:
            config.set_main_option('sqlalchemy.url', db_url)
    except RuntimeError:
        # --- Outside a Flask app context (e.g. plain `alembic` CLI), keep the ini URL ---
        pass
    engine = engine_from_config(config.get_section(config.config_ini_section), prefix='sqlalchemy.')
    connection = engine.connect()
    # --- Bind to the app's SQLAlchemy metadata so autogenerate sees all models ---
    context.configure(connection=connection, target_metadata=target_db.metadata)
    with context.begin_transaction():
        context.run_migrations()
    connection.close()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
