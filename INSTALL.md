# Dev installation

Typical installation with uv for development.

Install uv first then run:

``` bash
make sync
```

This runs `uv sync` and then installs `src/voteit_org` on top if it is checked out.
A plain `uv sync` removes voteit_org again.
