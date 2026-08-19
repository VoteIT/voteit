"""Dump the field shape of every pydantic model, for v1 -> v2 regression diffing.

Usage:
    python tools/pydantic_shapes.py > /tmp/shapes_v1.json     # before the flip
    python tools/pydantic_shapes.py > /tmp/shapes_v2.json     # after the flip
    diff <(jq -S . /tmp/shapes_v1.json) <(jq -S . /tmp/shapes_v2.json)

Any field that flips required False -> True is an implicit-Optional that was
missed: in pydantic v1 ``x: T | None`` with no default is optional, in v2 it is
required. Any flip True -> False is an accidentally introduced default.

Throwaway migration tool -- delete once the chanx/pydantic2 branch has landed.
"""

import json
import os
import re
import pkgutil
import sys
from importlib import import_module

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings_development")

import django  # noqa: E402

django.setup()

from pydantic import BaseModel  # noqa: E402

PACKAGES = ["voteit"]


def walk_models():
    seen: set[type] = set()
    for pkg_name in PACKAGES:
        pkg = import_module(pkg_name)
        for mod_info in pkgutil.walk_packages(pkg.__path__, f"{pkg_name}."):
            name = mod_info.name
            if ".migrations." in name or name.endswith(".migrations"):
                continue
            try:
                module = import_module(name)
            except Exception as exc:  # noqa: BLE001 - best effort inventory
                print(f"SKIP {name}: {exc}", file=sys.stderr)
                continue
            for obj in vars(module).values():
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseModel)
                    and obj is not BaseModel
                    and obj not in seen
                ):
                    seen.add(obj)
                    yield obj


VOLATILE = re.compile(r"datetime\.datetime\([^)]*\)")


def stable(default) -> str:
    """Normalise defaults whose repr is not stable across runs.

    e.g. ``created: datetime = now()`` evaluates at import time, so its repr
    differs between processes; only the required flag matters for the diff.
    """
    return VOLATILE.sub("<datetime>", repr(default))


def fields(model: type[BaseModel]):
    if hasattr(model, "model_fields"):  # pydantic v2
        return {
            name: [f.is_required(), stable(f.default)]
            for name, f in model.model_fields.items()
        }
    return {  # pydantic v1
        name: [f.required is True, stable(f.default)]
        for name, f in model.__fields__.items()
    }


def main():
    out = {}
    for model in walk_models():
        key = f"{model.__module__}.{model.__qualname__}"
        out[key] = fields(model)
    json.dump(out, sys.stdout, indent=1, sort_keys=True)
    print()


if __name__ == "__main__":
    main()
