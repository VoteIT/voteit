FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    --mount=type=bind,source=dist,target=dist \
    uv venv $VIRTUAL_ENV && \
    uv pip install -r requirements.txt && \
    uv pip install dist/*.whl --no-deps

# Clean stage
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=project.settings_production

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 555 voteit \
    && useradd -u 555 -g voteit --system --no-create-home voteit

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=voteit:voteit --chmod=+x manage.py docker-entrypoint.sh wait-for-it.sh ./
COPY --chown=voteit:voteit project ./project
COPY --chown=voteit:voteit locales ./locales

USER voteit

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["run"]
