# telethon-sqlalchemy-session

SQLAlchemy-backed session storage for Telethon. Store sessions in Postgres (or any SQLAlchemy-supported DB) instead of SQLite.

## Install (uv)

- Postgres (psycopg v3 extra):

```bash
uv add "telethon-sqlalchemy-session[postgres]"
```

- MySQL (PyMySQL extra):

```bash
uv add "telethon-sqlalchemy-session[mysql]"
```

For other databases, install the appropriate SQLAlchemy driver directly (not via this package), then use the correct engine URL (see Supported databases below).

## Quick start

```python
from telethon import TelegramClient
from telethon_sqlalchemy_session import SQLAlchemySession

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
from telethon_sqlalchemy_session import SQLAlchemySession

db_url = os.environ["TELETHON_DB_URL"]
session = SQLAlchemySession(db_url, session_name="prod-bot")
client = TelegramClient(session, api_id, api_hash)
```

## Listing sessions in a DB

```python
from telethon_sqlalchemy_session import SQLAlchemySession

names = SQLAlchemySession.list_sessions("postgresql+psycopg://user:pass@host/db")
print(names)
```

## Notes

- Schema is created automatically on first use.
- This package is synchronous. If you need async, open an issue.
- No migrations are required at this time.

## Develop & test (uv)

```bash
# from inside this package directory
uv run python -c "import telethon_sqlalchemy_session, sys; print('ok')"
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
uv run telethon-session-migrate one path/to/old.session "postgresql+psycopg://user:pass@host:5432/db" --session-name my_session
```

Directory (batch):

```bash
uv run telethon-session-migrate dir path/to/sessions "postgresql+psycopg://user:pass@host:5432/db"
```

- If `--session-name` is omitted for single-file mode, the name is derived from filename (e.g., `old.session` → `old`).
- Batch mode derives each session name from its filename.

## Supported databases and URLs

- Postgres (psycopg v3): URL `postgresql+psycopg://user:pass@host:5432/db`; install with `uv add "telethon-sqlalchemy-session[postgres]"`.
- MySQL (PyMySQL): URL `mysql+pymysql://user:pass@host:3306/db`; install with `uv add "telethon-sqlalchemy-session[mysql]"`.
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
