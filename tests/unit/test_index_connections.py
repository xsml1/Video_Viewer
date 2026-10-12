from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, get_ident

import pytest

from video_compare.media.index import FrameIndexRepository


def assert_closed(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_index_connections_commit_rollback_and_release_file(tmp_path: Path, monkeypatch) -> None:
    connect = sqlite3.connect
    retained_connections: list[sqlite3.Connection] = []

    def retained_connect(*args, **kwargs) -> sqlite3.Connection:
        connection = connect(*args, **kwargs)
        retained_connections.append(connection)
        return connection

    monkeypatch.setattr("video_compare.media.index.sqlite3.connect", retained_connect)
    path = tmp_path / "索引 文件.sqlite3"
    repository = FrameIndexRepository(path)
    with repository._connect() as connection:
        connection.execute("CREATE TABLE transaction_check (value TEXT)")
        connection.execute("INSERT INTO transaction_check VALUES ('committed')")
    assert_closed(connection)
    with pytest.raises(RuntimeError, match="abort transaction"), repository._connect() as failed:
        failed.execute("INSERT INTO transaction_check VALUES ('rolled back')")
        raise RuntimeError("abort transaction")
    assert_closed(failed)
    with repository._connect() as reader:
        assert reader.execute("SELECT value FROM transaction_check").fetchall() == [("committed",)]
    for retained in retained_connections:
        assert_closed(retained)
    # Keep strong references to every connection: success must not depend on GC.
    moved = path.rename(tmp_path / "重命名 索引.sqlite3")
    moved.unlink()
    assert not path.exists() and not moved.exists()


def test_index_connections_are_owned_and_closed_by_each_calling_thread(tmp_path: Path) -> None:
    path = tmp_path / "thread-index.sqlite3"
    repository = FrameIndexRepository(path)
    barrier = Barrier(2)

    def read_index() -> tuple[int, sqlite3.Connection]:
        with repository._connect() as connection:
            barrier.wait(timeout=5)
            assert connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall() == [("assets",), ("frames",)]
        assert_closed(connection)
        return get_ident(), connection

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(read_index) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]
    assert len({thread_id for thread_id, _connection in results}) == 2
    assert results[0][1] is not results[1][1]
    moved = path.rename(tmp_path / "closed-thread-index.sqlite3")
    moved.unlink()
