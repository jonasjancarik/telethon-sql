# telethon-sql

SQLAlchemy-backed session storage for Telethon. Store sessions in Postgres (or any SQLAlchemy-supported DB) instead of SQLite.

> Note: synchronous-only. Telethon's session interface is sync, and there is no async session variant. Use synchronous SQLAlchemy engines/drivers (async URLs/drivers are not supported).

## Install (uv) from GitHub

- **Postgres (psycopg v3 extra)**:

```bash
uv add 'telethon-sql[postgres] @ git+https://github.com/jonasjancarik/telethon-sql@main'
```

- **MySQL (PyMySQL extra)**:

```bash
uv add 'telethon-sql[mysql] @ git+https://github.com/jonasjancarik/telethon-sql@main'
```

For other databases, install the appropriate SQLAlchemy driver directly (not via this package), then use the correct engine URL (see Supported databases below).

## Quick start

```python
from telethon import TelegramClient
from telethon_sql import SQLAlchemySession

# Example Postgres URL (psycopg 3)
db_url = "postgresql+psycopg://user:password@localhost:5432/telethon"

# Give your logical session a name so multiple sessions can share one DB
session = SQLAlchemySession(db_url, session_name="my_session")

client = TelegramClient(session, api_id, api_hash)

with client:
    client.send_message("me", "Hello from SQLAlchemy session!")
```

- Data is scoped by `session_name` so one database can hold many Telethon sessions.
- The implementation mirrors Telethon's built-in `SQLiteSession` semantics.

## Environment variable example

```bash
export TELETHON_DB_URL="postgresql+psycopg://user:pass@localhost:5432/telethon"
```

```python
import os
from telethon import TelegramClient
from telethon_sql import SQLAlchemySession

db_url = os.environ["TELETHON_DB_URL"]
session = SQLAlchemySession(db_url, session_name="prod-bot")
client = TelegramClient(session, api_id, api_hash)
```

## Listing sessions in a DB

```python
from telethon_sql import SQLAlchemySession

names = SQLAlchemySession.list_sessions("postgresql+psycopg://user:pass@host/db")
print(names)
```

## Notes

- Schema is created automatically on first use.
- This package is synchronous-only. Telethon's session API is sync; async drivers/URLs and SQLAlchemy's AsyncEngine are not supported. If you need async, open an issue.
- No migrations are required at this time.

## Develop & test (uv)

```bash
# from inside this package directory
uv run python -c "import telethon_sql, sys; print('ok')"
```

## Build & publish (uv)

```bash
# Build wheel/sdist
uv build

# Publish to PyPI (requires credentials configured in uv)
uv publish
```

## Migrate legacy SQLite .session files

Single file:

```bash
uv run telethon-sql-migrate one path/to/old.session "postgresql+psycopg://user:pass@host:5432/db" --session-name my_session
```

Directory (batch):

```bash
uv run telethon-sql-migrate dir path/to/sessions "postgresql+psycopg://user:pass@host:5432/db"
```

Alternative (module form) if the console script is unavailable:

```bash
uv run -m telethon_sql.migrate one path/to/old.session "postgresql+psycopg://user:pass@host:5432/db" --session-name my_session
uv run -m telethon_sql.migrate dir path/to/sessions "postgresql+psycopg://user:pass@host:5432/db"
```

- If `--session-name` is omitted for single-file mode, the name is derived from filename (e.g., `old.session` → `old`).
- Batch mode derives each session name from its filename.

## Supported databases and URLs

- Postgres (psycopg v3): URL `postgresql+psycopg://user:pass@host:5432/db`; install with `uv add "telethon-sql[postgres]"`.
- MySQL (PyMySQL): URL `mysql+pymysql://user:pass@host:3306/db`; install with `uv add "telethon-sql[mysql]"`.
- SQLite: URL `sqlite:///path/to/file.db` or `sqlite:///:memory:`; no extra driver needed.
- MariaDB (mariadbconnector): URL `mariadb+mariadbconnector://user:pass@host:3306/db`; install with `uv add mariadb`.
- SQL Server (pyodbc): URL `mssql+pyodbc://user:pass@DSN` or `mssql+pyodbc:///?odbc_connect=...`; install with `uv add pyodbc`.
- Oracle (oracledb): URL `oracle+oracledb://user:pass@host:1521/service`; install with `uv add oracledb`.

Notes:
- Only Postgres and MySQL are provided as extras in this package; for other databases, install the driver directly.
- Any synchronous SQLAlchemy 2.x dialect should work. Just install the driver and use the appropriate URL.
- The session backend is synchronous; async drivers/URLs are not used.

## License

MIT
