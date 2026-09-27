# --- Build stage ---
# Stage 1 ("builder"): compile and install Python dependencies so the runtime stage can copy only the result.
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools needed to compile PyMySQL and cryptography C extensions.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements.txt first to leverage Docker layer caching for pip installs.
COPY backend/requirements.txt .
# Install dependencies into an isolated prefix so they can be copied wholesale into the runtime image.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Runtime stage ---
# Stage 2 ("runtime"): minimal image containing only the installed packages and the app code.
FROM python:3.11-slim AS runtime

# Install the MySQL client runtime library that PyMySQL links against at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the pre-built Python packages from the builder stage into the runtime image.
COPY --from=builder /install /usr/local

# Copy the rest of the project (app code, configs) into the image.
COPY . .

# Environment defaults for production: no .pyc files, unbuffered stdout for logging.
ENV FLASK_ENV=production
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose the port Gunicorn listens on.
EXPOSE ${PORT:-5000}

# Start Gunicorn using the production config in backend/gunicorn.conf.py, loading the app factory from backend.run:app.
CMD ["gunicorn", "--config", "backend/gunicorn.conf.py", "backend.run:app"]
