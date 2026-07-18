FROM python:3.11
ENV PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /usr/local/bin/

WORKDIR /usr/src/app

# Installed separately from the app source so dependency layers stay cached
# even when only the code changes (the bind mount in docker-compose.dev.yml
# overwrites /usr/src/app at runtime, but not /opt/venv).
COPY ./pyproject.toml ./uv.lock /usr/src/app/
RUN uv sync --frozen --no-install-project --group dev

COPY ./ /usr/src/app
RUN uv sync --frozen --group dev
