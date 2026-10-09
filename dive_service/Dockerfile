# CR 64 Part B / CR 65 · DIVE — its OWN Railway service (agapi-dive-demo), its own volume (/data) and DB. Build context = the repo root.
# It copies ONLY dive_service/: no agapi_service, no backend.
#
# Stage 1 (test): Microsoft's Playwright image — the unit tests AND EU 212's demo script played in a real Chromium (the failure beat
# included; the sandbox and the taverna as fakes, no network, no real phone). If anything fails, the image is never built.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy AS test
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY dive_service/requirements.txt /srv/dive_service/requirements.txt
RUN pip install --no-cache-dir -r /srv/dive_service/requirements.txt playwright==1.47.0
COPY dive_service /srv/dive_service
RUN rm -f /srv/dive_service/dive.db* && python -m unittest -v dive_service.tests.test_dive dive_service.tests.test_e2e 2>&1 | tail -40 \
    && python -m unittest dive_service.tests.test_dive dive_service.tests.test_e2e && touch /srv/tests-passed

# Stage 2 (the service): slim — no browser. It needs stage 1's marker, so a failed test stops the build.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY dive_service/requirements.txt /srv/dive_service/requirements.txt
RUN pip install --no-cache-dir -r /srv/dive_service/requirements.txt
COPY dive_service /srv/dive_service
COPY --from=test /srv/tests-passed /srv/tests-passed
RUN rm -f /srv/dive_service/dive.db*
CMD ["sh", "-c", "exec python -m uvicorn dive_service.app:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
