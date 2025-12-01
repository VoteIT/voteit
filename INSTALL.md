# Dev installation

Typical installation with venv and poetry for development.

``` python

python3.12 -m venv venv
source venv/bin/activate
pip install -U pip poetry
poetry install --with dev

```

Notes:
setuptools is a temp dependency, we need to refactor python3-vote-core
