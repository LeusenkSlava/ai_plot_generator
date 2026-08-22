ARG PYTHON_VERSION=3.13
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-trixie-slim

ARG APP_VERSION=develop
ARG ENVIRONMENT="prod"
ARG USER_UID=1000
ARG USER_GID=1000

ENV APP_VERSION=${APP_VERSION}
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_HTTP_TIMEOUT=300
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

# Установка системных зависимостей
RUN if [ "${ENVIRONMENT}" = "prod" ]; then \
      uv sync --frozen --no-cache --no-dev --no-install-project; \
    else \
      uv sync --frozen --no-cache --dev --no-install-project; \
    fi

COPY . .

RUN if [ "${ENVIRONMENT}" = "prod" ]; then \
      uv sync --frozen --no-cache --no-dev; \
    else \
      uv sync --frozen --no-cache --dev; \
    fi

RUN groupadd -g ${USER_GID} runner \
    && useradd -u ${USER_UID} -g runner -m -s /usr/sbin/nologin runner \
    && chown -R runner:runner /app \
    && chmod -R g=u /app

USER runner

EXPOSE 8000

ENTRYPOINT [ "/app/docker-entrypoint.sh" ]
