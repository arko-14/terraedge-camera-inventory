# Single-image deployment: the React app is built and then served by the
# FastAPI process, so the whole thing runs on one origin behind one URL.
# No CORS, a plain SameSite=Lax session cookie, and one service to wake up on
# a free tier instead of two.

# --- stage 1: build the frontend -------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build

# Copy manifests first so `npm ci` is cached until dependencies actually change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Empty base URL: the app calls /api on its own origin.
ENV VITE_API_BASE_URL=""
RUN npm run build


# --- stage 2: the application ----------------------------------------------
FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# The built app lands where STATIC_DIR points.
COPY --from=frontend /build/dist ./static
ENV STATIC_DIR=/app/static

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Render (and most platforms) inject $PORT; default to 8000 locally.
# Migrations run on start, so the schema is never behind the code.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
