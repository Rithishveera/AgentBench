FROM python:3.12-slim AS sandbox

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git passwd \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

RUN python -m pip install --no-cache-dir --disable-pip-version-check \
    pytest==8.3.5 \
    pytest-asyncio==1.1.0 \
    pytest-cov==6.2.1 \
    pytest-timeout==2.4.0 \
    requests==2.32.5

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin sandbox

WORKDIR /workspace
USER 10001:10001