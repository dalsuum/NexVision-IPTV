FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements_prod.txt ./
RUN pip install --no-cache-dir -r requirements_prod.txt

COPY . .

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:5000/vod/api/health || exit 1

CMD ["gunicorn", "--worker-class", "gevent", "--workers", "5", "--worker-connections", "1000", "--bind", "0.0.0.0:5000", "--timeout", "120", "wsgi:application"]
