ARG PYTHON_IMAGE=python@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY services/sample_mcps/requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir -r requirements.lock.txt && pip check
COPY contracts/mcp-tools.schema.json /app/contracts/mcp-tools.schema.json
COPY services/sample_mcps /app/services/sample_mcps
COPY tests/sample_mcps /app/tests/sample_mcps
COPY scripts/m4 /app/scripts/m4
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "services.sample_mcps.inventory"]
