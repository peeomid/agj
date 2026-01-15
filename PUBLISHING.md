# Publishing AGJ (using uv)

## One-time setup
- Ensure you own the `agj` project on PyPI (or adjust the name if it’s taken).
- Create a PyPI token (recommended) or configure trusted publishing on GitHub.

## Build
```
uv build
```

Artifacts will appear in `dist/`.

## Publish (manual)
```
uv publish
```

## Optional: TestPyPI
```
uv publish --repository testpypi
```

## Notes
- `agj` is defined by `[project.scripts]` in `pyproject.toml`.
- Users can install via `pipx install agj` for an isolated CLI.
