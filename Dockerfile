# ClientVerse full-stack production image: React SPA + FastAPI API served from one HTTPS origin.
FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/yarn.lock ./
RUN corepack enable && yarn install --frozen-lockfile
COPY frontend/ ./
# Leave empty so browser API calls resolve to same-origin /api.
ENV REACT_APP_BACKEND_URL=""
RUN CI=true yarn build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_BUILD_DIR=/app/frontend/build \
    APP_ENV=production \
    SEED_DEMO_DATA=false \
    PORT=8000

WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend/ /app/backend/
COPY --from=frontend-build /build/frontend/build /app/frontend/build

WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
