ARG PYTHON_IMAGE=python:3.13.5-slim-bookworm@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419
FROM ${PYTHON_IMAGE} AS runtime
WORKDIR /app
COPY backend/requirements.lock.txt /app/backend/requirements.lock.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.lock.txt && pip check
COPY backend /app/backend
COPY contracts /app/contracts
RUN useradd --uid 10001 --create-home urumi
USER 10001
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000

FROM runtime AS checks
COPY scripts/m5 /app/scripts/m5
COPY scripts/m6 /app/scripts/m6
COPY scripts/m7 /app/scripts/m7
CMD ["python", "-m", "scripts.m5.harness"]

# Release cannot fall back to an isolated test harness.
FROM runtime AS release
RUN test -f /app/backend/main.py && test -f /app/backend/orchestrator.py
CMD ["python", "-m", "backend.main"]
