# CR 64 Part B · DIVE — its OWN Railway service (agapi-dive-demo), its own volume (/data) and DB. Build context = the repo root.
# It copies ONLY dive_service/: no agapi_service, no backend. The build runs DIVE's tests: an image that fails them never ships.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY dive_service/requirements.txt /srv/dive_service/requirements.txt
RUN pip install --no-cache-dir -r /srv/dive_service/requirements.txt
COPY dive_service /srv/dive_service
RUN rm -f /srv/dive_service/dive.db* && python -m unittest dive_service.tests.test_dive
CMD ["sh", "-c", "exec python -m uvicorn dive_service.app:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
