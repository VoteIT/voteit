# Dev installation

Typical installation with uv for development.

Install uv first then run:

``` bash
make sync
```

This runs `uv sync` and then installs every package checked out under `src/` (e.g. `voteit_org`) on top.
A plain `uv sync` removes them again.
