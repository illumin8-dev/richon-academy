FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
WORKDIR /app
RUN test -s "$SSL_CERT_FILE" && groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY main.py db.py orders.py migrate_orders.py auth_core.py auth_http.py portal.py portal_store.py monthly_store.py monthly_portal.py manual_models.py manual_store.py manual_portal.py ./
COPY migrations/ ./migrations/
COPY portal_static/ ./portal_static/
USER 10001:10001
EXPOSE 8080
CMD ["sh", "-c", "exec python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --no-access-log --no-proxy-headers"]
