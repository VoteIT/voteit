# Base images are pinned by digest so a rebuild of an old tag cannot silently
# change what lands in the image. Dependabot (.github/dependabot.yml) bumps
# these; without it, security updates to the base stop arriving.
FROM python:3.13-slim@sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0 AS builder
# This copies an executable that then runs as root during the build, so it is
# the last place to accept a floating tag.
COPY --from=ghcr.io/astral-sh/uv:0.12.9@sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=src/voteit_org,target=src/voteit_org \
    --mount=type=bind,source=dist,target=dist \
    uv sync --frozen --no-dev --group docker --no-install-workspace --no-install-project && \
    uv pip install dist/*.whl --no-deps

# Clean stage
FROM python:3.13-slim@sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=project.settings_production

# Removing pip is not housekeeping, it pulls in debian-built packages that already has fixes for no reason.
#
# libmagic1 is python-magic's shared library; it has no wheel to bundle it.

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /usr/local/lib/python3.13/site-packages/pip /usr/local/bin/pip* \
    && groupadd -g 555 voteit \
    && useradd -u 555 -g voteit --system --no-create-home voteit \
    && mkdir -p /app/media \
    && chown voteit:voteit /app/media

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=voteit:voteit --chmod=+x manage.py docker-entrypoint.sh wait-for-it.sh ./
COPY --chown=voteit:voteit project ./project
COPY --chown=voteit:voteit locales ./locales

USER voteit

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["run"]
