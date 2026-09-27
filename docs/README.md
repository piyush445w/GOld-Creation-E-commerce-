# Gold Creation - E-Commerce Platform

A full-featured e-commerce platform built with Flask, SQLAlchemy, and Tailwind CSS for selling Indian women's ethnic wear and home textiles.

## Tech Stack

- **Backend**: Flask 3.0, Flask-SQLAlchemy, Flask-Login, Flask-WTF, Flask-Mail
- **Database**: MySQL 8.0 (via PyMySQL)
- **Frontend**: Jinja2, Tailwind CSS, Lucide icons
- **Scheduler**: APScheduler
- **Payments**: Razorpay (INR), PayPal (international)
- **Notifications**: Twilio (SMS/WhatsApp), Flask-Mail (email)
- **Currency**: Admin-managed exchange rates

## Prerequisites

- Python 3.10+
- MySQL 8.0+
- pip

## Installation

1. Clone or copy the project to your local machine.

2. Create a virtual environment:
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Linux/Mac:
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

4. Create a `.env` file in the project root (copy from `backend/.env.example`):
   ```bash
   copy backend\.env.example .env
   ```

5. Configure your `.env` file with your settings:
   - Database connection string
   - Mail server credentials
   - Twilio credentials (optional)
   - Razorpay and PayPal keys
   - Admin credentials for seed.py (optional — seed.py provides defaults)
     - `ADMIN_EMAIL`: email address for the default admin user
     - `ADMIN_PASSWORD`: password for the default admin user
   - Note: `SECRET_KEY` and `DATABASE_URL` must be set explicitly in production and testing.
     Fallbacks are only provided in the development config for convenience.

6. Create the MySQL database:
   ```sql
   CREATE DATABASE gold_creation CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

## Setup

### Seed Database
```bash
cd backend && python seed.py
```

This creates all tables and seeds initial data (currencies, site settings).
It also creates a default admin user using `ADMIN_EMAIL` and `ADMIN_PASSWORD`
from your `.env` file (defaults to `admin@goldcreation.com` / `admin123` if not set).

### Create Admin User
```bash
cd backend && python create_admin.py
```

Follow the prompts to create your first admin account.

## Running the Application

```bash
cd backend && python run.py
```

The app will be available at `http://localhost:5000`.

- Storefront: `http://localhost:5000`
- Admin panel: `http://localhost:5000/admin`
- Admin login: `http://localhost:5000/auth/admin/login`

## Project Structure

```
gold_creation/
+-- frontend/
¦   +-- templates/
¦   ¦   +-- base.html
¦   ¦   +-- storefront/
¦   ¦   +-- admin/
¦   +-- static/
¦       +-- css/
¦       +-- js/
¦       +-- images/
¦       +-- videos/
+-- backend/
¦   +-- app/
¦   ¦   +-- __init__.py
¦   ¦   +-- config.py
¦   ¦   +-- models/
¦   ¦   +-- routes/
¦   ¦   +-- utils/
¦   ¦   +-- templates/  (if any remain)
¦   +-- migrations/
¦   +-- tests/
¦   +-- run.py
¦   +-- seed.py
¦   +-- create_admin.py
¦   +-- requirements.txt
¦   +-- ...
+-- docs/
¦   +-- README.md
+-- docker-compose.yml
+-- Dockerfile
+-- .env
```

> **Note:** Backend code lives in `backend/` and frontend assets (Jinja2 templates and static files) live in `frontend/`. Run all Python commands from inside `backend/` or prefix them with `cd backend &&`.

## Key Features

### Storefront
- Responsive product catalog with category filtering
- Product detail with mixed image/video gallery
- Shopping cart with guest support
- Wishlist functionality
- Two-currency support (INR, USD) with live conversion
- Checkout with guest account creation
- Order history and tracking
- CMS pages

### Admin Panel
- Product management with mixed media galleries (images + videos)
- Category management with festival collections
- Order management with status updates
- Coupon management with category restrictions
- CMS page management
- Site settings (theme, contact, social)
- Banner management
- Navigation menu management
- Customer management
- Review moderation
- Global media library

### Notifications
- Order confirmation emails
- Password reset emails
- Abandoned cart reminders
- SMS/WhatsApp order notifications (via Twilio)

## Scheduled Jobs
- Daily currency rate refresh
- Abandoned cart reminder emails (every 24 hours)

## Notes
- Prices are stored in INR in the database. Only INR and USD currencies are supported.
- Guest users can checkout and an account is auto-created
- Admin accounts can only be created via seed script or by existing admins

## License
Proprietary - Gold Creation


