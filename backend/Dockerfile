FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY requirements.txt ./

# 官方源在部分网络下不可达；CI 保持默认官方源，本地可通过 build-arg 指定镜像源
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN python -m pip install --no-cache-dir --upgrade pip -i "${PIP_INDEX_URL}" \
    && python -m pip install --no-cache-dir -r requirements.txt -i "${PIP_INDEX_URL}"

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN mkdir -p /app/app/uploads /app/app/private_uploads && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import json, urllib.request; data = json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)); raise SystemExit(0 if data.get('database') == 'connected' else 1)"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}\""]
