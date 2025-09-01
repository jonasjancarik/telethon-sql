import argparse
import os
import sqlite3
from typing import Optional

from .session import SQLAlchemySession


def migrate_sqlite_to_sqlalchemy(
    sqlite_path: str, db_url: str, session_name: Optional[str] = None
) -> None:
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(sqlite_path)

    # Infer default session_name from filename (without extension) if not provided
    if not session_name:
        base = os.path.basename(sqlite_path)
        if base.endswith(".session"):
            base = base[:-8]
        session_name = base or "default"

    conn = sqlite3.connect(sqlite_path)
    try:
        cur = conn.cursor()

        # Initialize destination session (creates schema if needed)
        dst = SQLAlchemySession(db_url, session_name=session_name)

        # Load sessions table
        cur.execute(
            "select dc_id, server_address, port, auth_key, takeout_id from sessions"
        )
        row = cur.fetchone()
        if row:
            dc_id, server_address, port, auth_key, takeout_id = row
            dst.set_dc(dc_id, server_address, port)
            if auth_key:
                # AuthKey expects raw bytes; Telethon stores raw bytes
                from telethon.crypto import AuthKey

                dst.auth_key = AuthKey(data=auth_key)
            dst.takeout_id = takeout_id

        # Migrate entities
        try:
            cur.execute("select id, hash, username, phone, name, date from entities")
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            rows = []

        if rows:
            # Use internal methods that mirror SQLiteSession semantics
            from telethon_sqlalchemy_session.session import Entity
            import time as _time

            now_ts = int(_time.time())

            # Insert preserving most recent username
            from sqlalchemy import select, update

            with dst._SessionLocal() as s:  # type: ignore[attr-defined]
                for ent_id, ent_hash, username, phone, name, date in rows:
                    s.merge(
                        Entity(
                            session_name=dst.session_name,
                            id=ent_id,
                            hash=ent_hash,
                            username=(username.lower() if username else None),
                            phone=phone,
                            name=name,
                            date=date or now_ts,
                        )
                    )
                    if username:
                        dups = s.execute(
                            select(Entity.id, Entity.date)
                            .where(Entity.session_name == dst.session_name)
                            .where(Entity.username == username.lower())
                            .order_by(Entity.date.asc().nullsfirst())
                        ).all()
                        if len(dups) > 1:
                            ids_to_null = [t[0] for t in dups[:-1]]
                            if ids_to_null:
                                s.execute(
                                    update(Entity)
                                    .where(Entity.session_name == dst.session_name)
                                    .where(Entity.id.in_(ids_to_null))
                                    .values(username=None)
                                )
                s.commit()

        # Migrate update_state
        try:
            cur.execute("select id, pts, qts, date, seq from update_state")
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            rows = []

        for eid, pts, qts, date, seq in rows:
            from telethon.tl import types as tl_types
            import datetime

            state = tl_types.updates.State(
                pts=pts,
                qts=qts,
                date=datetime.datetime.fromtimestamp(date),
                seq=seq,
                unread_count=0,
            )
            dst.set_update_state(eid, state)

        # Migrate sent_files
        try:
            cur.execute("select md5_digest, file_size, type, id, hash from sent_files")
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            rows = []

        from telethon.tl.types import InputPhoto, InputDocument
        from telethon.sessions.memory import _SentFileType as _SFT

        for md5_digest, file_size, type_value, fid, fh in rows:
            if type_value == _SFT.DOCUMENT.value:
                dst.cache_file(md5_digest, file_size, InputDocument(fid, fh))
            elif type_value == _SFT.PHOTO.value:
                dst.cache_file(md5_digest, file_size, InputPhoto(fid, fh))

    finally:
        conn.close()


def migrate_directory(dir_path: str, db_url: str) -> None:
    if not os.path.isdir(dir_path):
        raise NotADirectoryError(dir_path)
    for entry in os.listdir(dir_path):
        if entry.endswith(".session"):
            src = os.path.join(dir_path, entry)
            try:
                migrate_sqlite_to_sqlalchemy(src, db_url, None)
                print(f"Migrated: {src}")
            except Exception as e:
                print(f"Failed: {src} -> {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate Telethon .session (SQLite) to SQLAlchemy-backed storage"
    )
    sub = parser.add_subparsers(dest="cmd")

    one = sub.add_parser("one", help="Migrate a single .session file")
    one.add_argument("sqlite_path", help="Path to legacy .session file")
    one.add_argument("db_url", help="SQLAlchemy DB URL (e.g., postgresql+psycopg://...")
    one.add_argument(
        "--session-name",
        dest="session_name",
        help="Target session_name (defaults to filename)",
    )

    batch = sub.add_parser("dir", help="Migrate all .session files in a directory")
    batch.add_argument("dir_path", help="Directory containing .session files")
    batch.add_argument(
        "db_url", help="SQLAlchemy DB URL (e.g., postgresql+psycopg://..."
    )

    args = parser.parse_args()

    if args.cmd == "one":
        migrate_sqlite_to_sqlalchemy(args.sqlite_path, args.db_url, args.session_name)
    elif args.cmd == "dir":
        migrate_directory(args.dir_path, args.db_url)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
