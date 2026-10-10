# CR 58 · the AgAPI sandbox — its own Railway service (agapi-sandbox). Test mode only; 0 live calls (recorded fixtures).
# Build context = the repo root (it imports Sasha's search code from backend/, never the agent loop).
# The build RUNS the conformance vectors and the service tests: an image that fails them never ships.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# CR 64 · the quickstart runs in CI (EU's ask): curl + jq for the curl snippet, Node 22 (types stripped) for the TypeScript one
RUN apt-get update && apt-get install -y --no-install-recommends curl jq uuid-runtime && rm -rf /var/lib/apt/lists/*
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
WORKDIR /srv
COPY agapi_service/requirements.txt /srv/agapi_service/requirements.txt
RUN pip install --no-cache-dir -r /srv/agapi_service/requirements.txt
COPY backend/booking_signer /srv/backend/booking_signer
COPY backend/app /srv/backend/app
COPY backend/scripts /srv/backend/scripts
COPY backend/agapi/__init__.py backend/agapi/powers.py backend/agapi/keep.py /srv/backend/agapi/
COPY agapi_service /srv/agapi_service
RUN rm -f /srv/agapi_service/sandbox.db* && python -m unittest agapi_service.tests.test_vectors agapi_service.tests.test_service agapi_service.tests.test_powers agapi_service.tests.test_cr62 agapi_service.tests.test_keep agapi_service.tests.test_quickstart agapi_service.tests.test_fixtures agapi_service.tests.test_docs agapi_service.tests.test_cr69 agapi_service.tests.test_cr70 agapi_service.tests.test_cr72 agapi_service.tests.test_cr73 agapi_service.tests.test_cr74
CMD ["sh", "-c", "exec python -m uvicorn agapi_service.app:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
