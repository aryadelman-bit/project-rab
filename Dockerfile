FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY data ./seed-data
COPY docs ./docs
COPY README.md ./

EXPOSE 8000

CMD ["sh", "scripts/docker-entrypoint.sh"]
