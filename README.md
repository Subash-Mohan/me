# Byte Journal

Single-user, chat-first personal journaling app with a memory layer.

See `CLAUDE.md` for the project briefing and `Plans/phases/` for the implementation roadmap.

## Quick start

```sh
git clone <repo>
cd "Me"
uv sync
uv run pre-commit install
uv run pytest
```

## Common commands

```sh
uv run ruff check .             # lint
uv run ruff format .            # format
uv run ty check app             # type check
uv run pytest                   # tests
```
