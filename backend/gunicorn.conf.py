import os

# gunicorn.conf.py - Production WSGI server configuration for Gunicorn.
# Used by the Docker CMD: gunicorn --config gunicorn.conf.py run:app
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"           # Listen on all interfaces inside the container on port 5000.
workers = 3                      # Number of sync worker processes (a small fixed pool suits CPU-bound + I/O work).
timeout = 120                    # Worker timeout in seconds; long requests (image uploads) get this much time.
accesslog = '-'                  # Log HTTP access lines to stdout (captured by the container runtime).
errorlog = '-'                   # Log errors and tracebacks to stdout as well.
loglevel = 'info'                # Verbosity level; 'info' is enough for production monitoring.
capture_output = True            # Capture stdout/stderr from workers so Gunicorn can report worker crashes.
