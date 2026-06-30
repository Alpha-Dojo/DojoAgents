# Release Build

## Wheel Build

```bash
uv build
```

Or:

```bash
python -m pip install build
python -m build
```

The build process runs the dashboard frontend build and bundles `web/dist/` into the wheel.

## Install Wheel

```bash
uv pip install dist/dojoagents-0.0.1-py3-none-any.whl
```

