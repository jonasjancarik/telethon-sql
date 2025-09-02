import datetime
import time

from typing import Generator, Iterable, Optional, Tuple

from telethon.tl import types as tl_types
from telethon.sessions.memory import MemorySession, _SentFileType
from telethon import utils
from telethon.crypto import AuthKey
from telethon.tl.types import (
    InputPhoto,
    InputDocument,
    PeerUser,
    PeerChat,
    PeerChannel,
)

try:
    from sqlalchemy import (
        Column,
        Integer,
        BigInteger,
        String,
        LargeBinary,
        create_engine,
        UniqueConstraint,
        select,
        update,
        delete,
        func,
    )
    from sqlalchemy.orm import declarative_base, sessionmaker, Session as SASession

    _sqlalchemy_err = None
except Exception as e:  # pragma: no cover - import-time guard only
    Column = Integer = BigInteger = String = LargeBinary = create_engine = (
        UniqueConstraint
    ) = select = update = delete = func = None
    declarative_base = sessionmaker = SASession = None
    _sqlalchemy_err = type(e)


DATABASE_VERSION = 1

Base = declarative_base() if declarative_base else None


class Version(Base):  # type: ignore[misc]
    __tablename__ = "version"

    version = Column(Integer, primary_key=True)


class SessionRow(Base):  # type: ignore[misc]
    __tablename__ = "sessions"

    session_name = Column(String(255), primary_key=True)
    dc_id = Column(Integer)
    server_address = Column(String(255))
    port = Column(Integer)
    auth_key = Column(LargeBinary)
    takeout_id = Column(Integer)


class Entity(Base):  # type: ignore[misc]
    __tablename__ = "entities"

    session_name = Column(String(255), primary_key=True)
    id = Column(BigInteger, primary_key=True)
    hash = Column(BigInteger, nullable=False)
    username = Column(String(255), nullable=True, index=True)
    phone = Column(String(64), nullable=True)
    name = Column(String(255), nullable=True)
    date = Column(Integer, nullable=True)


class SentFile(Base):  # type: ignore[misc]
    __tablename__ = "sent_files"

    session_name = Column(String(255), primary_key=True)
    md5_digest = Column(LargeBinary, primary_key=True)
    file_size = Column(Integer, primary_key=True)
    type = Column(Integer, primary_key=True)
    id = Column(BigInteger)
    hash = Column(BigInteger)


class UpdateState(Base):  # type: ignore[misc]
    __tablename__ = "update_state"

    session_name = Column(String(255), primary_key=True)
    id = Column(BigInteger, primary_key=True)
    pts = Column(Integer)
    qts = Column(Integer)
    date = Column(Integer)
    seq = Column(Integer)


class SQLAlchemySession(MemorySession):
    """
    Session backend for Telethon powered by SQLAlchemy.

    Stores session data keyed by `session_name` so multiple Telethon sessions can
    share a single database (e.g., PostgreSQL). Any SQLAlchemy-supported engine
    URL is valid.
    """

    def __init__(self, db_url: str, session_name: str = "default"):
        if _sqlalchemy_err is not None:
            raise _sqlalchemy_err

        super().__init__()
        self._engine = create_engine(db_url, future=True)
        self._SessionLocal = sessionmaker(
            bind=self._engine, expire_on_commit=False, class_=SASession, future=True
        )
        self.session_name = session_name
        self.save_entities = True

        self._ensure_schema()
        self._load_existing_session()

    def clone(self, to_instance=None):
        cloned = super().clone(to_instance)
        cloned.save_entities = self.save_entities
        if isinstance(cloned, SQLAlchemySession):
            cloned.session_name = self.session_name
        return cloned

    # region Schema / Setup

    def _ensure_schema(self) -> None:
        Base.metadata.create_all(self._engine)
        with self._SessionLocal() as s:
            existing = s.get(Version, DATABASE_VERSION)
            if not existing:
                # Initialize or upgrade version row. Keep it simple and single-row.
                # If older versions are ever needed, migration logic would go here.
                s.merge(Version(version=DATABASE_VERSION))
                s.commit()

    def _load_existing_session(self) -> None:
        with self._SessionLocal() as s:
            row = s.get(SessionRow, self.session_name)
            if row:
                self._dc_id = row.dc_id or 0
                self._server_address = row.server_address
                self._port = row.port
                self._takeout_id = row.takeout_id
                self._auth_key = AuthKey(data=row.auth_key) if row.auth_key else None

            else:
                # Create initial session row
                s.merge(
                    SessionRow(
                        session_name=self.session_name,
                        dc_id=self._dc_id,
                        server_address=self._server_address,
                        port=self._port,
                        auth_key=b"",
                        takeout_id=self._takeout_id,
                    )
                )
                s.commit()

    # endregion

    # region Session core state

    def set_dc(self, dc_id, server_address, port):
        super().set_dc(dc_id, server_address, port)
        self._update_session_row()
        # Fetch auth_key for current (single) DC stored in sessions row
        with self._SessionLocal() as s:
            row = s.get(SessionRow, self.session_name)
            if row and row.auth_key:
                self._auth_key = AuthKey(data=row.auth_key)
            else:
                self._auth_key = None

    @MemorySession.auth_key.setter
    def auth_key(self, value):
        self._auth_key = value
        self._update_session_row()

    @MemorySession.takeout_id.setter
    def takeout_id(self, value):
        self._takeout_id = value
        self._update_session_row()

    def _update_session_row(self) -> None:
        with self._SessionLocal() as s:
            s.merge(
                SessionRow(
                    session_name=self.session_name,
                    dc_id=self._dc_id,
                    server_address=self._server_address,
                    port=self._port,
                    auth_key=self._auth_key.key if self._auth_key else b"",
                    takeout_id=self._takeout_id,
                )
            )
            s.commit()

    # endregion

    # region Update state

    def get_update_state(self, entity_id):
        with self._SessionLocal() as s:
            row = s.get(
                UpdateState, {"session_name": self.session_name, "id": entity_id}
            )
            if row:
                date = (
                    datetime.datetime.fromtimestamp(row.date, tz=datetime.timezone.utc)
                    if row.date
                    else None
                )
                return tl_types.updates.State(
                    row.pts, row.qts, date, row.seq, unread_count=0
                )

    def set_update_state(self, entity_id, state):
        with self._SessionLocal() as s:
            s.merge(
                UpdateState(
                    session_name=self.session_name,
                    id=entity_id,
                    pts=state.pts,
                    qts=state.qts,
                    date=int(state.date.timestamp()) if state.date else None,
                    seq=state.seq,
                )
            )
            s.commit()

    def get_update_states(self) -> Iterable[Tuple[int, tl_types.updates.State]]:
        with self._SessionLocal() as s:
            rows = (
                s.execute(
                    select(UpdateState).where(
                        UpdateState.session_name == self.session_name
                    )
                )
                .scalars()
                .all()
            )
            return (
                (
                    r.id,
                    tl_types.updates.State(
                        pts=r.pts,
                        qts=r.qts,
                        date=datetime.datetime.fromtimestamp(
                            r.date, tz=datetime.timezone.utc
                        )
                        if r.date
                        else None,
                        seq=r.seq,
                        unread_count=0,
                    ),
                )
                for r in rows
            )

    # endregion

    # region Persistence lifecycle

    def save(self):
        # Each operation commits; explicit save is a no-op but kept for interface parity
        pass

    def close(self):
        # Dispose engine connections if any are open
        if self._engine:
            self._engine.dispose()

    def delete(self):
        with self._SessionLocal() as s:
            s.execute(
                delete(SentFile).where(SentFile.session_name == self.session_name)
            )
            s.execute(delete(Entity).where(Entity.session_name == self.session_name))
            s.execute(
                delete(UpdateState).where(UpdateState.session_name == self.session_name)
            )
            s.execute(
                delete(SessionRow).where(SessionRow.session_name == self.session_name)
            )
            s.commit()
        return True

    @classmethod
    def list_sessions(cls, db_url: str) -> Iterable[str]:
        if _sqlalchemy_err is not None:
            raise _sqlalchemy_err
        engine = create_engine(db_url, future=True)
        SessionLocal = sessionmaker(
            bind=engine, expire_on_commit=False, class_=SASession, future=True
        )
        try:
            with SessionLocal() as s:
                if not engine.dialect.has_table(
                    engine.connect(), SessionRow.__tablename__
                ):
                    return []
                names = s.execute(select(SessionRow.session_name)).scalars().all()
                return list(sorted(set(names)))
        finally:
            engine.dispose()

    # endregion

    # region Entities

    def process_entities(self, tlo):
        if not self.save_entities:
            return
        rows = self._entities_to_rows(tlo)
        if not rows:
            return
        now_ts = int(time.time())
        with self._SessionLocal() as s:
            for ent_id, ent_hash, username, phone, name in rows:
                s.merge(
                    Entity(
                        session_name=self.session_name,
                        id=ent_id,
                        hash=ent_hash,
                        username=username,
                        phone=phone,
                        name=name,
                        date=now_ts,
                    )
                )

                if username:
                    # Evict older duplicates for the same username within the same session
                    dups = s.execute(
                        select(Entity.id, Entity.date)
                        .where(Entity.session_name == self.session_name)
                        .where(Entity.username == username)
                        .order_by(Entity.date.asc().nullsfirst())
                    ).all()
                    if len(dups) > 1:
                        # Keep the newest one (last), null others
                        ids_to_null = [row[0] for row in dups[:-1]]
                        if ids_to_null:
                            s.execute(
                                update(Entity)
                                .where(Entity.session_name == self.session_name)
                                .where(Entity.id.in_(ids_to_null))
                                .values(username=None)
                            )

            s.commit()

    def get_entity_rows_by_phone(self, phone):
        with self._SessionLocal() as s:
            row = s.execute(
                select(Entity.id, Entity.hash)
                .where(Entity.session_name == self.session_name)
                .where(Entity.phone == phone)
            ).first()
            return row if row else None

    def get_entity_rows_by_username(self, username):
        with self._SessionLocal() as s:
            results = s.execute(
                select(Entity.id, Entity.hash, Entity.date)
                .where(Entity.session_name == self.session_name)
                .where(Entity.username == username)
            ).all()
            if not results:
                return None
            if len(results) > 1:
                results.sort(key=lambda t: t[2] or 0)
                ids_to_null = [t[0] for t in results[:-1]]
                if ids_to_null:
                    s.execute(
                        update(Entity)
                        .where(Entity.session_name == self.session_name)
                        .where(Entity.id.in_(ids_to_null))
                        .values(username=None)
                    )
                    s.commit()
            return results[-1][0], results[-1][1]

    def get_entity_rows_by_name(self, name):
        with self._SessionLocal() as s:
            row = s.execute(
                select(Entity.id, Entity.hash)
                .where(Entity.session_name == self.session_name)
                .where(Entity.name == name)
            ).first()
            return row if row else None

    def get_entity_rows_by_id(self, id, exact=True):
        with self._SessionLocal() as s:
            if exact:
                row = s.execute(
                    select(Entity.id, Entity.hash)
                    .where(Entity.session_name == self.session_name)
                    .where(Entity.id == id)
                ).first()
                return row if row else None
            else:
                row = s.execute(
                    select(Entity.id, Entity.hash)
                    .where(Entity.session_name == self.session_name)
                    .where(
                        Entity.id.in_(
                            [
                                utils.get_peer_id(PeerUser(id)),
                                utils.get_peer_id(PeerChat(id)),
                                utils.get_peer_id(PeerChannel(id)),
                            ]
                        )
                    )
                ).first()
                return row if row else None

    def get_input_entity(self, key):
        # Delegate to MemorySession logic, which uses our get_entity_rows_* methods
        return super().get_input_entity(key)

    # endregion

    # region File cache

    def get_file(self, md5_digest, file_size, cls):
        with self._SessionLocal() as s:
            row = s.execute(
                select(SentFile.id, SentFile.hash)
                .where(SentFile.session_name == self.session_name)
                .where(SentFile.md5_digest == md5_digest)
                .where(SentFile.file_size == file_size)
                .where(SentFile.type == _SentFileType.from_type(cls).value)
            ).first()
            if row:
                return cls(row[0], row[1])

    def cache_file(self, md5_digest, file_size, instance):
        if not isinstance(instance, (InputDocument, InputPhoto)):
            raise TypeError("Cannot cache %s instance" % type(instance))
        with self._SessionLocal() as s:
            s.merge(
                SentFile(
                    session_name=self.session_name,
                    md5_digest=md5_digest,
                    file_size=file_size,
                    type=_SentFileType.from_type(type(instance)).value,
                    id=instance.id,
                    hash=instance.access_hash,
                )
            )
            s.commit()

    # endregion
