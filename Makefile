# Shell / Make config
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

.SILENT:
MAKEFLAGS += --no-print-directory

# -----------------------------
# User-configurable variables (edit this)
# INFRA_SERVICES: long-running infra (db, broker, cache, ...)
# INFRA_INIT_SERVICES: one-shot services that prepare INFRA_SERVICES
# MIGRATION_DB_SERVICE: transactional db service used by alembic (empty = no migrations)
# STAIRWAY_TEST: path to stairway test (empty = skip stairway step)
# -----------------------------
PROJECT_NAME ?= $(notdir $(abspath .))

# -----------------------------
# Internal vars / aliases
# -----------------------------
DOCKER_COMPOSE := docker compose -p $(PROJECT_NAME)
DOCKER_ENV := scripts/makefile/docker_env.sh
DOCKER_PRUNE := scripts/makefile/docker_prune.sh

# Docker compose
.PHONY: docker-env upd up down stop
docker-env:
	$(DOCKER_ENV)

upd: docker-env
	$(DOCKER_COMPOSE) up -d --build --force-recreate

up: docker-env
	$(DOCKER_COMPOSE) up --build --force-recreate

just_up: docker-env
	$(DOCKER_COMPOSE) up -d

start: docker-env
	$(DOCKER_COMPOSE) start

restart: docker-env
	$(DOCKER_COMPOSE) restart

down:
	$(DOCKER_COMPOSE) down

stop:
	$(DOCKER_COMPOSE) stop

.PHONY: prune
prune:
	$(DOCKER_PRUNE)
