# CR 58 · the AgAPI sandbox — its own Railway service (agapi-sandbox). Test mode only; 0 live calls (recorded fixtures).
# Build context = the repo root (it imports Sasha's search code from backend/, never the agent loop).
# The build RUNS the conformance vectors and the service tests: an image that fails them never ships.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY agapi_service/requirements.txt /srv/agapi_service/requirements.txt
RUN pip install --no-cache-dir -r /srv/agapi_service/requirements.txt
COPY backend/booking_signer /srv/backend/booking_signer
COPY backend/app /srv/backend/app
COPY backend/scripts /srv/backend/scripts
COPY backend/agapi/__init__.py backend/agapi/powers.py /srv/backend/agapi/
COPY agapi_service /srv/agapi_service
RUN rm -f /srv/agapi_service/sandbox.db* && python -m unittest agapi_service.tests.test_vectors agapi_service.tests.test_service agapi_service.tests.test_powers
CMD ["sh", "-c", "exec python -m uvicorn agapi_service.app:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
