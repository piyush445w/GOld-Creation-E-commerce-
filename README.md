# Gold Creation

Full-stack e-commerce platform for ethnic wear & home textiles.

## Tech Stack
- **Backend:** Flask 2.3, SQLAlchemy, MySQL 8.0, Alembic
- **Frontend:** Jinja2, Tailwind CSS (CDN), custom JavaScript
- **Payments:** Razorpay (INR), PayPal (international)
- **Notifications:** Twilio (SMS/WhatsApp)
- **Deployment:** Render (web), Railway (MySQL), Docker

## Quick Start

### Prerequisites
- Python 3.11+
- MySQL 8.0+ (or Docker)
- Node.js 18+ (optional, for Tailwind build if needed)

### Local Development
```bash
# 1. Clone
git clone <repo-url>
cd gold_creation

# 2. Configure environment
cp .env.example .env
# Edit .env with your database credentials

# 3. Start database (Docker)
docker compose -f backend/docker-compose.yml up -d db

# 4. Install dependencies
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt

# 5. Run migrations
cd backend
flask db upgrade
cd ..

# 6. Seed database (optional)
cd backend && python seed.py && cd ..

# 7. Start dev server
cd backend && python run.py
```

## Deployment
See [`deployment.md`](deployment.md) for Render + Railway setup.
See [`deployment/render.yaml`](deployment/render.yaml) for Render Blueprint config.

## Documentation
See [`docs/README.md`](docs/README.md) for full architecture and feature list.

## License
[Add your license here]
# GOld-Creation-E-commerce-
