FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
#RUN apt-get update && apt-get install -y \
#    build-essential \
#    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml manage.py .
# Install dependencies in the image so devs don't run them manually
# Create a mock voteit dir, the volume will overwrite it later. This is to avoid reinstall every time.
RUN mkdir voteit &&\
    touch voteit/__init__.py README.md &&\
    pip install --upgrade pip &&\
    pip install poetry && \
    poetry config virtualenvs.create false
COPY poetry.lock .
RUN poetry install
