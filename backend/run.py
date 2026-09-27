# run.py - Development server entry point.
# Run with: python run.py
# Loads .env, creates the Flask app, starts the APScheduler, then runs the dev server on port 5000.
import os
# Change to the backend directory so relative paths (templates, media) resolve correctly.
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
from app import create_app
from app.utils.scheduler import start_scheduler

# Load environment variables from .env in backend/ first, then fall back to project root.
backend_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(backend_dir, '.env'))
load_dotenv(os.path.join(backend_dir, '..', '.env'))  # Fallback to project root

# Create the Flask app instance; FLASK_ENV controls config (development/production/testing).
app = create_app(os.getenv('FLASK_ENV', 'development'))

if __name__ == '__main__':
    # Start scheduled jobs (e.g. daily currency refresh, abandoned-cart emails) within an app context.
    with app.app_context():
        start_scheduler()
    # Run the Flask development server; debug mode is controlled by the app config.
    app.run(debug=app.config.get("DEBUG", False), port=5000)
