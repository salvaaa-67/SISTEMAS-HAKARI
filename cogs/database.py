"""Camada fina sobre o sqlite3 da biblioteca padrão, com a mesma API do asyncpg
que os cogs já usavam (execute, executemany, fetch, fetchrow, fetchval,
acquire().transaction()). Assim as consultas continuam usando $1, $2...

Não exige nenhuma dependência extra: o sqlite3 roda em uma thread separada
(asyncio.to_thread) para não bloquear o event loop.
"""
from __future__ import annotations

import asyncio
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

# Segundos desde a época Unix (substitui NOW() do PostgreSQL)
UNIX_NOW = "CAST(strftime('%s', 'now') AS INTEGER)"

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "hakari.db"

_PLACEHOLDER = re.compile(r"\$(\d+)")

Record = sqlite3.Row


def database_path() -> Path:
    """Caminho do arquivo SQLite (variável SQLITE_PATH sobrescreve o padrão)."""
    configured = os.getenv("SQLITE_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_DB_PATH


def _translate(query: str) -> str:
    # $1 -> ?1 (o SQLite aceita parâmetros numerados, então a ordem é preservada)
    return _PLACEHOLDER.sub(r"?\1", query)


class _Connection:
    def __init__(self, raw: sqlite3.Connection) -> None:
        self._raw = raw

    async def execute(self, query: str, *args: Any) -> None:
        await asyncio.to_thread(self._execute, query, args)

    async def executemany(self, query: str, args: Iterable[Iterable[Any]]) -> None:
        await asyncio.to_thread(self._executemany, query, list(args))

    async def fetch(self, query: str, *args: Any) -> list[sqlite3.Row]:
        return await asyncio.to_thread(self._fetch, query, args)

    async def fetchrow(self, query: str, *args: Any) -> sqlite3.Row | None:
        rows = await asyncio.to_thread(self._fetch, query, args)
        return rows[0] if rows else None

    async def fetchval(self, query: str, *args: Any) -> Any:
        row = await _Connection.fetchrow(self, query, *args)
        return row[0] if row is not None else None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        await asyncio.to_thread(self._raw.execute, "BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            await asyncio.to_thread(self._raw.execute, "ROLLBACK")
            raise
        else:
            await asyncio.to_thread(self._raw.execute, "COMMIT")

    # --- execução síncrona (roda dentro de to_thread) ---
    def _execute(self, query: str, args: tuple) -> None:
        self._raw.execute(_translate(query), args).close()

    def _executemany(self, query: str, args: list) -> None:
        if not args:
            return
        in_transaction = self._raw.in_transaction
        if not in_transaction:
            self._raw.execute("BEGIN IMMEDIATE")
        try:
            self._raw.executemany(_translate(query), args)
        except BaseException:
            if not in_transaction:
                self._raw.execute("ROLLBACK")
            raise
        if not in_transaction:
            self._raw.execute("COMMIT")

    def _fetch(self, query: str, args: tuple) -> list[sqlite3.Row]:
        cursor = self._raw.execute(_translate(query), args)
        try:
            return cursor.fetchall()
        finally:
            cursor.close()


class Pool(_Connection):
    """Uma única conexão serializada por lock (suficiente para um bot do Discord)."""

    def __init__(self, raw: sqlite3.Connection) -> None:
        super().__init__(raw)
        self._lock = asyncio.Lock()

    async def execute(self, query: str, *args: Any) -> None:
        async with self._lock:
            await super().execute(query, *args)

    async def executemany(self, query: str, args: Iterable[Iterable[Any]]) -> None:
        async with self._lock:
            await super().executemany(query, args)

    async def fetch(self, query: str, *args: Any) -> list[sqlite3.Row]:
        async with self._lock:
            return await super().fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> sqlite3.Row | None:
        async with self._lock:
            return await _Connection.fetchrow(self, query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        async with self._lock:
            return await _Connection.fetchval(self, query, *args)

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[_Connection]:
        # Segura o lock durante todo o bloco para que a transação seja isolada.
        async with self._lock:
            yield _Connection(self._raw)

    async def close(self) -> None:
        await asyncio.to_thread(self._raw.close)


async def create_pool(path: str | Path | None = None) -> Pool:
    target = Path(path) if path else database_path()

    def _open() -> sqlite3.Connection:
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(
            target,
            timeout=20,
            isolation_level=None,  # autocommit; transações são explícitas
            check_same_thread=False,
        )
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA synchronous=NORMAL")
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("PRAGMA busy_timeout=20000")
        return raw

    return Pool(await asyncio.to_thread(_open))
