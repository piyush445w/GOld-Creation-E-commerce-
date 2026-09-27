# Gold Creation — Deployment Guide

Host the Gold Creation Flask app on **Render** (web service) with **MySQL** provided by **Railway**.

---

## 1. Overview

```
[Client Browser]
      |
      | HTTPS
      v
[Render Web Service]  ---- mysql+pymysql over SSL ---->  [Railway MySQL]
  - Gunicorn + Flask                               - MySQL 8.x / 5.7
  - backend/run:app                                - Private VPC / public
  - Environment Variables                           - Automated backups
```

**Components:**
- **Render Web Service:** Runs the Flask API. Render provides the `$PORT` env var.
- **Railway MySQL:** Managed MySQL database. Connection requires SSL (Railway uses self-signed SSL certificates).
- **GitHub:** Source of truth. Render deploys from a connected GitHub repo.

---

## 2. Prerequisites

- A **GitHub repository** containing this project.
- A **Render account** (free tier is sufficient to start; paid for persistent disk/always-on).
- A **Railway account** to provision the managed MySQL service.
- (Optional) A **Twilio** account, **Razorpay** / **PayPal** developer accounts, and an **SMTP** provider for full feature parity.

---

## 3. Step 1: Provision MySQL on Railway

1. Log in to the [Railway Dashboard](https://railway.app/dashboard).
2. Click **New** ? **MySQL** to create a new MySQL instance.
3. Choose a plan and a region near your Render deployment.
4. Wait for the service to provision (~1–2 min).

**Collect connection details** from the **Railway Dashboard** under your MySQL service ? **Connect**:

| Variable | Railway Field | Example |
|----------|---------------|---------|
| Host | MySQL Host | `mysql.railway.internal` |
| Port | MySQL Port | `3306` |
| User | MySQL User | `root` |
| Password | MySQL Password | (from Railway dashboard) |
| Database | Railway Database | `railway` |

**SSL:**
- Railway MySQL uses self-signed SSL certificates.
- Railway MySQL connections from external services (like Render) require SSL.
- The app auto-configures SSL for Railway/Aiven hosts; do not add `ssl_mode` to `DATABASE_URL`.

Example connection string:
```bash
mysql+pymysql://root:password@mysql.railway.internal:3306/railway
```

`config.py` passes SSL settings via SQLAlchemy `connect_args` so PyMySQL receives them correctly.

**Create the database (if not auto-created):**
- Railway usually auto-creates the default database you specified. If not, connect with a MySQL client and run:

```sql
CREATE DATABASE IF NOT EXISTS gold_creation;
```

---

## 4. Step 2: Prepare the Codebase

1. **Confirm no PostgreSQL references remain.** The project now uses MySQL exclusively.
2. **Verify the `DATABASE_URL` format.** It should follow:

```bash
mysql+pymysql://<user>:<password>@<host>:<port>/<database>
```

Example for Railway:

```bash
mysql+pymysql://root:mysecret@mysql.railway.internal:3306/railway
```

3. Ensure `requirements.txt` includes `PyMySQL` and `cryptography` (needed for SSL).

4. Commit and push all changes to GitHub.

---

## 5. Step 3: Deploy the Web Service on Render

### 5.1 Create a New Web Service

1. In the Render Dashboard, click **New** ? **Web Service**.
2. Connect your **GitHub repository** and authorize Render.
3. Select the repository and branch (e.g., `main`).

### 5.2 Configure Build & Start

| Setting                | Value                                                                                   |
|------------------------|-----------------------------------------------------------------------------------------|
| Name                   | `gold-creation` (or your preference)                                                    |
| Region                 | Same region as your Railway MySQL (e.g., `US East`, `eu-central-1`)                      |
| Runtime                | **Python 3**                                                                             |
| Build Command          | `pip install -r requirements.txt`                                               |
| Start Command          | `gunicorn --bind 0.0.0.0:\$PORT --config gunicorn.conf.py run:app`      |
| Plan                   | **Starter** (or higher)                                                                  |

**Important notes:**
- Render injects the `$PORT` environment variable automatically at runtime. The app must listen on `0.0.0.0:$PORT`.
- Do **not** hardcode port `5000` in the Render start command; use `$PORT`.

### 5.3 Set Environment Variables

In the **Environment** section of the Render dashboard, add the following:

| Variable                  | Description                                                                                            | Example / Notes                                                                 |
|---------------------------|--------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| `SECRET_KEY`              | Flask secret key for sessions and CSRF protection.                                                      | Generate a strong random string.                                                |
| `DATABASE_URL`            | Full MySQL connection string for Railway.                                                                 | `mysql+pymysql://root:pass@mysql.railway.internal:3306/railway` |
| `MAIL_SERVER`             | SMTP server hostname.                                                                                   | `smtp.gmail.com`                                                                |
| `MAIL_PORT`               | SMTP port (587 for TLS, 465 for SSL).                                                                   | `587`                                                                           |
| `MAIL_USE_TLS`            | Enable TLS for SMTP.                                                                                    | `true`                                                                          |
| `MAIL_USERNAME`           | SMTP username / email address.                                                                          | `your-email@gmail.com`                                                          |
| `MAIL_PASSWORD`           | SMTP app password or API key.                                                                           | `your-app-password`                                                             |
| `TWILIO_ACCOUNT_SID`      | Twilio Account SID (for SMS / WhatsApp notifications).                                                  | `ACxxxx...`                                                                     |
| `TWILIO_AUTH_TOKEN`       | Twilio Auth Token.                                                                                      | `your-twilio-token`                                                             |
| `TWILIO_PHONE_NUMBER`     | Twilio phone number in E.164 format.                                                                    | `+1234567890`                                                                   |
| `TWILIO_WHATSAPP_NUMBER`  | Twilio WhatsApp sandbox / sender number.                                                                | `+1234567890`                                                                   |
| `RAZORPAY_KEY_ID`         | Razorpay Key ID (INR payments).                                                                         | `rzp_test_xxxx`                                                                 |
| `RAZORPAY_KEY_SECRET`     | Razorpay Key Secret.                                                                                    | `your-razorpay-secret`                                                          |
| `PAYPAL_CLIENT_ID`        | PayPal REST Client ID (international payments).                                                         | `your-paypal-client-id`                                                         |
| `PAYPAL_CLIENT_SECRET`    | PayPal REST Client Secret.                                                                              | `your-paypal-secret`                                                            |
| `PAYPAL_MODE`             | PayPal environment.                                                                                     | `sandbox` (or `live`)                                                           |
| `ADMIN_EMAIL`             | Admin email used by `seed.py` / `create_admin.py`.                                                      | `admin@goldcreation.com`                                                        |
| `ADMIN_PASSWORD`          | Admin password used by `create_admin.py`.                                                               | `your-strong-password`                                                          |
| `FLASK_ENV`               | Set to `production` to disable debug mode.                                                              | `production`                                                                    |

**Tip:** Render allows you to add environment variables in bulk. Copy/paste the key-value pairs above.

### 5.4 Railway MySQL SSL Configuration

Railway MySQL uses self-signed SSL certificates. The app auto-configures SSL for Railway/Aiven hosts via SQLAlchemy `connect_args`, so you do not need to append `ssl_mode` to `DATABASE_URL`.

Example `DATABASE_URL`:

```bash
mysql+pymysql://root:mysecret@mysql.railway.internal:3306/railway
```

`config.py` detects `railway.internal` / `railway.app` hosts and adds the required SSL settings automatically.

---

## 6. Step 4: Run Database Migrations

After the first deploy (or after any schema changes), run Flask-Migrate on Render.

### 6.1 Using Render Shell (Interactive)

1. In Render Dashboard, go to your web service ? **Shell** tab.
2. Run:

```bash
python -m flask --app run db upgrade
```

### 6.2 Using a One-Off Job (if Shell is unavailable)

Render also supports **Background Workers** or **Cron Jobs**, but the simplest approach for a one-time command is the Shell. Alternatively, you can trigger it via a temporary endpoint or use Render's **SSH** feature.

### 6.3 Locally Against Railway

```bash
export DATABASE_URL="mysql+pymysql://root:pass@mysql.railway.internal:3306/railway"
cd backend
python -m flask db upgrade
```

---

## 7. Step 5: Seed the Database

### 7.1 Seed Initial Data

Run `seed.py` to populate reference data:

```bash
python -m flask --app run seed
```

Or directly:

```bash
python backend/seed.py
```

### 7.2 Create the Admin User

Run `create_admin.py` interactively:

```bash
python backend/create_admin.py
```

Follow the prompts to set the admin email and password.

> **Tip:** On Render, you can run these in the **Shell** tab. If you prefer automation, wrap them in a small script and execute via a temporary worker or the shell.

---

## 8. Step 6: Verify Deployment

1. **Health Check:** Open `https://<your-service>.onrender.com/health`. Expect a `200 OK` response.
2. **API Docs:** Check `https://<your-service>.onrender.com/api/docs` or your app's documented endpoints.
3. **Admin Login:** Navigate to `/admin` (or your login route) and sign in with the credentials from `seed.py` / `create_admin.py`.
4. **Database Connection:** Verify order creation, product listing, or any database-backed route returns data without errors.

---

## 9. Local Development Setup (Optional)

### Option A: Docker Compose (Local MySQL)

From the `backend/` directory:

```bash
cd backend
docker-compose up --build
```

This spins up a local MySQL container and connects the Flask app to it. Access the app at `http://localhost:5000`.

### Option B: Local MySQL + `.env`

1. Install MySQL locally and create the `gold_creation` database.
2. Copy `backend/.env.example` to `backend/.env`.
3. Update `DATABASE_URL`:

```bash
DATABASE_URL=mysql+pymysql://root:@localhost/gold_creation
```

4. Run migrations and seed:

```bash
cd backend
python -m flask db upgrade
python backend/seed.py
python backend/create_admin.py
python run.py
```

---

## 10. Railway-Specific Notes

### SSL Configuration

Railway MySQL uses self-signed SSL certificates. The app auto-configures SSL for Railway/Aiven hosts via `SQLALCHEMY_ENGINE_OPTIONS` in `config.py`, so you do not need to add `ssl_mode` to `DATABASE_URL`.

```python
# backend/app/config.py
if 'railway.internal' in host or 'railway.app' in host:
    connect_args['ssl'] = {'ssl_mode': 'REQUIRED'}
```

### Connection Pooling

SQLAlchemy's default pool size is usually fine for a single Render web service. If you see connection exhaustion:

```python
# In backend/app/config.py
SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_size": 10,
    "max_overflow": 5,
    "pool_recycle": 1800,
    "pool_pre_ping": True,
}
```

### Constructing `DATABASE_URL`

Always use this format:

```bash
mysql+pymysql://<user>:<password>@<host>:<port>/<database>
```

URL-encode special characters in the password (e.g., `@` ? `%40`, `#` ? `%23`). The app handles SSL automatically for known hosts.

---

## 11. Troubleshooting

### Database Connection Errors

| Symptom                                      | Likely Cause                                             | Fix                                                                 |
|----------------------------------------------|----------------------------------------------------------|---------------------------------------------------------------------|
| `Can't connect to MySQL server on 'host'`    | Wrong host / port / firewall block.                      | Verify Railway **Connection info**. Ensure Render IP is allowed if Railway uses IP whitelisting. |
| `SSL connection error`                       | SSL params in URL passed to PyMySQL incorrectly.                  | Ensure `ssl_mode` is not in `DATABASE_URL`. The app configures SSL via engine options. |
| `Unknown MySQL server host`                  | Typo in hostname.                                        | Double-check the Railway hostname (it ends in `railway.internal`).    |
| `Access denied for user 'root'`          | Wrong password or database not created.                  | Reset password in Railway. Ensure the database exists.               |

### Migration Issues

| Symptom                                      | Likely Cause                                             | Fix                                                                 |
|----------------------------------------------|----------------------------------------------------------|---------------------------------------------------------------------|
| `Can't locate revision`                      | Migration history mismatch.                              | Ensure `migrations/` is committed. Run `flask db stamp head` on the new DB first if needed. |
| `Target database is not up to date`          | Running `upgrade` before `init` or on wrong environment. | Verify `FLASK_ENV=production`. Check that `migrations/versions/` exists in the repo. |

### Media Upload Path Issues

| Symptom                                      | Likely Cause                                             | Fix                                                                 |
|----------------------------------------------|----------------------------------------------------------|---------------------------------------------------------------------|
| Images not showing / `FileNotFoundError`     | Upload path is relative to `backend/` instead of `frontend/media/` or `instance/`. | Ensure upload paths in `config.py` or app code are absolute. On Render, use `/tmp/uploads` or a mounted disk for transient files. For persistent files, consider using **Render Disks** or an external storage service (e.g., S3, Cloudinary). |
| `frontend/media` vs `backend/frontend/media` | Frontend is served as static files, but media is saved relative to the app root. | Normalize paths: use `os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'media')` or absolute paths. Verify the `UPLOAD_FOLDER` config value. |

### General Tips

- **Check Render Logs:** The **Logs** tab in Render shows Gunicorn / Flask output. Errors here often reveal missing env vars or DB connection failures.
- **Render Shell:** Use the **Shell** tab to run ad-hoc commands like `python -m flask --app run db upgrade` without needing to redeploy.
- **Railway Metrics:** Monitor connections, CPU, and memory in the Railway dashboard.
- **Secrets Management:** Never hardcode secrets in code. Always use environment variables or Render's secret file feature.

---

## Quick Reference

| Task                          | Command                                                                                     |
|-------------------------------|---------------------------------------------------------------------------------------------|
| Run migrations                | `python -m flask --app run db upgrade`                                              |
| Seed data                     | `python backend/seed.py`                                                                     |
| Create admin                  | `python backend/create_admin.py`                                                             |
| Start dev server locally      | `python backend/run.py`                                                                      |
| Build Docker image            | `docker build -f backend/Dockerfile -t gold-creation .`                                     |
| Run with Docker Compose       | `cd backend && docker-compose up --build`                                                   |
| Test health endpoint          | `curl https://<service>.onrender.com/health`                                                 |

---
