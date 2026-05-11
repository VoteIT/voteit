.DEFAULT_GOAL := install
.ONESHELL:
.PHONY: build dev

install:
	cat INSTALL.md
requirements:
	uv export --no-dev --frozen --no-install-workspace --group docker --no-annotate --no-header -q -o requirements.txt
	uvx pip-audit -r requirements.txt --disable-pip
shell:
	python manage.py shell
coverage:
	coverage run && coverage report
migrations:
	python manage.py makemigrations
migrate:
	python manage.py migrate
rqworker:
	python manage.py devrqworker default ts conn long --with-scheduler
up:
	docker compose up -d
	python manage.py rqworker --with-scheduler default ts conn &
	python -W once manage.py runserver
down:
	docker compose down
run:
	python -W once manage.py runserver
test:
	python manage.py test voteit --keepdb --failfast
test-deps:
	python manage.py test dialects voteit_org --keepdb --failfast
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
	OAUTHLIB_INSECURE_TRANSPORT=1 \
	ID_HOST=http://localhost:8001 \
	DJANGO_SETTINGS_MODULE=project.settings \
	HOST=.voteit.se \
	&& python manage.py test voteit --keepdb --failfast
