.DEFAULT_GOAL := install

install: venv
	poetry install --with dev
venv:
	test -d venv || virtualenv -p python3 venv
	. venv/bin/activate
requirements:
	poetry export -o requirements.txt --with docker --without-hashes
coverage: venv
	coverage run && coverage report
migrations: venv
	python manage.py makemigrations
migrate: venv
	python manage.py migrate
rqworker: venv
	python manage.py devrqworker default ts conn --with-scheduler
up: venv
	docker compose up -d
	python manage.py rqworker --with-scheduler default ts conn &
	python -W once manage.py runserver
down:
	docker compose down
run:
	python -W once manage.py runserver
test:
	./manage.py test voteit voteit_org dialect_tests voteit_tools --keepdb --failfast
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
	&& ./manage.py test voteit --keepdb --failfast
