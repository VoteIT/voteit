.DEFAULT_GOAL := install
.ONESHELL:
.PHONY: build dev

install:
	cat INSTALL.md
audit:
	tmp=$$(mktemp) && uv export --frozen --no-dev --no-install-workspace --group docker --no-annotate --no-header -q -o $$tmp && uvx pip-audit -r $$tmp --disable-pip; rm -f $$tmp
shell:
	python manage.py shell
migrations:
	python manage.py makemigrations
migrate:
	python manage.py migrate
rqworker:
	python manage.py devrqworker default long --with-scheduler
up:
	docker compose up -d
	python manage.py rqworker --with-scheduler default long &
	python -W once manage.py runserver
down:
	docker compose down
run:
	python -W once manage.py runserver
# `make test` runs the whole voteit suite; `make test voteit.messaging` runs just
# that target. The same goes for `make coverage`. Extra words on the command line
# are swallowed by the catch-all rule below (only enabled when test or coverage is
# the first goal) instead of being treated as goals.
TEST_TARGET := $(or $(filter-out test,$(MAKECMDGOALS)),voteit)
COVERAGE_TARGET := $(or $(filter-out coverage,$(MAKECMDGOALS)),voteit)
COVERAGE_PATH := $(subst .,/,$(COVERAGE_TARGET))
test:
	REDIS_CACHE_LOCATION=redis://127.0.0.1:6379/9 POSTGRES_PORT=5433 python manage.py test $(TEST_TARGET) --keepdb --failfast
# Passing the command line explicitly overrides [tool.coverage.run] command_line.
# The report is limited to the target's own files: measurement still covers all of
# `source` (voteit), so without --include every untouched module would be listed.
coverage:
	REDIS_CACHE_LOCATION=redis://127.0.0.1:6379/9 POSTGRES_PORT=5433 coverage run manage.py test $(COVERAGE_TARGET) --keepdb && coverage report --include="$(COVERAGE_PATH)/*,$(COVERAGE_PATH).py"
ifneq (,$(filter $(firstword $(MAKECMDGOALS)),test coverage))
%:
	@:
endif
test-deps:
	REDIS_CACHE_LOCATION=redis://127.0.0.1:6379/9 POSTGRES_PORT=5433 python manage.py test voteit_org --keepdb --failfast
build:
	uv build --all-packages -o ./dist
dev: build
	set -e
	docker pull python:3.13-slim
	docker build . -t voteit/voteit4dev:dev
messages:
	cd voteit && python ../manage.py makemessages  -l sv -i=.venv -i=src
compilemessages:
	cd voteit && python ../manage.py compilemessages -i=.venv -i=src
envtest:
	export DJANGO_DEBUG=1 \
	POSTGRES_HOST=127.0.0.1 \
	POSTGRES_PORT=5433 \
	OAUTHLIB_INSECURE_TRANSPORT=1 \
	ID_HOST=http://localhost:8001 \
	DJANGO_SETTINGS_MODULE=project.settings \
	HOST=.voteit.se \
	&& python manage.py test voteit --keepdb --failfast
