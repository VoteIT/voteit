.DEFAULT_GOAL := install
.ONESHELL:

install:
	cat INSTALL.md
requirements:
	poetry export -o requirements.txt --with docker --without-hashes
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
	python manage.py test dialect_tests voteit_org --keepdb --failfast
build:
	set -e
	poetry build --format wheel
	poetry build --format wheel -o ../../dist -P src/voteit_org
	poetry build --format wheel -o ../../dist -P src/member_dialects
dev: build
	set -e
	docker pull python:3.12-slim
	docker build . -t voteit/voteit4dev:dev
envtest:
	export DJANGO_DEBUG=1 \
	POSTGRES_HOST=127.0.0.1 \
	OAUTHLIB_INSECURE_TRANSPORT=1 \
	ID_HOST=http://localhost:8001 \
	DJANGO_SETTINGS_MODULE=project.settings \
	HOST=.voteit.se \
	&& python manage.py test voteit --keepdb --failfast
