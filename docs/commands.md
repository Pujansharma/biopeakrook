# Commands Reference

Commonly used `uv` and Django management commands for this project.

> **Prerequisites:** Activate the virtual environment before running any command.
> ```bash
> source .venv/Scripts/activate  # Windows (Git Bash / WSL)
> .venv\Scripts\activate          # Windows (CMD / PowerShell)
> ```

---

## Dependencies

```bash
# Install / sync dependencies from uv.lock
uv sync

# Upgrade all packages to their latest versions and re-lock
uv sync --upgrade

# Re-generate uv.lock without installing (e.g. after manual pyproject.toml edits)
uv lock
```

> Use `uv add <package>` to add a new dependency. Never use `pip install`.

---

## Static Files

```bash
# Collect static files (wipes the target dir first)
uv run manage.py collectstatic --noinput --clear
```

---

## Development Server

Run with the default settings (development) or override with `--settings`.

```bash
# Default (development settings, localhost only)
uv run manage.py runserver

# Staging / production settings
uv run manage.py runserver --settings=core.settings.staging
uv run manage.py runserver --settings=core.settings.production

# Bind to all interfaces (useful for Docker or LAN access)
uv run manage.py runserver 0.0.0.0:8000
uv run manage.py runserver 0.0.0.0:8000 --settings=core.settings.staging
uv run manage.py runserver 0.0.0.0:8000 --settings=core.settings.production
```

> For production-like testing, prefer Gunicorn or the ASGI server below over `runserver`.

---

## ASGI Server (Uvicorn)

```bash
uv run uvicorn core.asgi:application --host 0.0.0.0 --port 8000
```

---

## Database Migrations

```bash
# Generate migration files for any model changes
uv run manage.py makemigrations

# Apply pending migrations
uv run manage.py migrate

# Apply migrations against staging / production databases
uv run manage.py migrate --settings=core.settings.staging
uv run manage.py migrate --settings=core.settings.production
```

> Always run `makemigrations` locally and commit the generated files before deploying.

---

## Superuser

```bash
# Create an admin superuser interactively
uv run manage.py createsuperuser
```

---

## Django Shell

```bash
# Interactive shell (development)
uv run manage.py shell

# Shell against staging / production databases
uv run manage.py shell --settings=core.settings.staging
uv run manage.py shell --settings=core.settings.production
```

---

## Data Fixtures

```bash
# Export all data except contenttypes (UTF-8 safe on Windows)
uv run -Xutf8 manage.py dumpdata -e contenttypes > data.json

# Import data from a fixture file
uv run manage.py loaddata data.json
```

> The `-Xutf8` flag is required on Windows to avoid encoding errors when writing the JSON file.