# create_admin.py - Interactive script for creating the first admin account.
# Run with: python create_admin.py
# Prompts for email, password (hidden), and name, then inserts a User with role='admin'.
import os
import sys
# Ensure the backend directory is on sys.path so `from app import ...` works when run directly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import getpass
from app import create_app, db
from app.models.user import User
from werkzeug.security import generate_password_hash

# Create the Flask app using the FLASK_ENV environment variable (defaults to development).
app = create_app(os.getenv('FLASK_ENV', 'development'))

with app.app_context():
    # Prompt the operator for the new admin's credentials.
    email = input('Admin email: ')
    # getpass hides the password from the terminal and from shoulder-surfers.
    password = getpass.getpass('Admin password: ')
    name = input('Admin name: ')

    # Guard against duplicate admin accounts with the same email address.
    existing = User.query.filter_by(email=email).first()
    if existing:
        print('User with this email already exists.')
        exit(1)

    # Hash the password with Werkzeug before storing it; never store plaintext.
    admin = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        role='admin'
    )
    db.session.add(admin)
    db.session.commit()
    print(f'Admin user created: {email}')
