ARG PYTHON_IMAGE=python:3.13.5-slim-bookworm
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY services/woocommerce_mcp/requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir -r requirements.lock.txt && pip check
COPY contracts/mcp-tools.schema.json /app/contracts/mcp-tools.schema.json
COPY services/woocommerce_mcp /app/services/woocommerce_mcp
COPY tests/woocommerce_mcp /app/tests/woocommerce_mcp
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "services.woocommerce_mcp.server"]
