# -*- coding: utf-8 -*-
# utils package — shared platform infrastructure for Gold Creation
# -----------------------------------------------------------------------------
# Houses cross-cutting helpers used by routes, the app factory and scheduled
# jobs: currency/FX utilities, email and SMS notification senders, upload
# validation & in-DB media storage, the APScheduler, and Jinja template
# helpers. Kept side-effect free so importing the package is safe.