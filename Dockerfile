ARG PYTHON_VERSION=3.13
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-trixie-slim

ARG APP_VERSION=develop
ARG USER_UID=1000
ARG USER_GID=1000

ENV APP_VERSION=${APP_VERSION}
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

RUN uv sync --frozen --no-cache --no-install-project

COPY . .

RUN uv sync --frozen --no-cache

RUN groupadd -g ${USER_GID} runner \
  && useradd -u ${USER_UID} -g runner -m -s /usr/sbin/nologin runner \
  && mkdir -p /opt/venv /opt/uv \
  && chown -R runner:runner /app /opt/venv /opt/uv \
  && chmod -R g=u /app /opt/venv /opt/uv

USER runner

EXPOSE 8000

ENTRYPOINT [ "/app/docker-entrypoint.sh" ]
