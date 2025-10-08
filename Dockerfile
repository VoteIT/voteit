FROM python:3.12-slim as builder
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir
COPY dist dist
RUN pip install dist/* --no-cache-dir --no-deps

# Clean stage
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV VIRTUAL_ENV=/opt/venv
RUN set -e; \
    addgroup --gid 555 voteit; \
    adduser --system --no-create-home --disabled-login --disabled-password --gid 555 --uid 555 voteit; \
    extra_deps='curl'; \
    apt-get update; \
    apt-get install -y --no-install-recommends $extra_deps; \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
COPY manage.py .
COPY docker-entrypoint.sh .
COPY wait-for-it.sh .
COPY project project
EXPOSE 8000
USER voteit
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["run"]
