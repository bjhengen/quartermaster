FROM python:3.13-slim

WORKDIR /app

# Install Oracle Instant Client dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libaio1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY plugins/ plugins/

ENV PYTHONPATH=/app/src:/app
ENV QM_ENV=production

ENTRYPOINT ["python", "-m", "quartermaster"]
