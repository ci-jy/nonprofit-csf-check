"""Throwaway PostgreSQL clusters for tests and local runs.

Starts ``initdb``/``pg_ctl`` from the local PostgreSQL install in a temporary
directory, listening only on a Unix socket, and removes it afterwards.
"""

from __future__ import annotations

import contextlib
import glob
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def find_pg_bin() -> Path | None:
    if shutil.which("initdb") and shutil.which("pg_ctl"):
        return Path(shutil.which("initdb")).parent
    candidates = sorted(glob.glob("/usr/lib/postgresql/*/bin/initdb"), reverse=True)
    candidates += sorted(glob.glob("/opt/homebrew/opt/postgresql*/bin/initdb"), reverse=True)
    return Path(candidates[0]).parent if candidates else None


@contextlib.contextmanager
def temporary_postgres(port: int = 25432):
    bindir = find_pg_bin()
    if bindir is None:
        raise RuntimeError("PostgreSQL server binaries (initdb, pg_ctl) not found")
    root = Path(tempfile.mkdtemp(prefix="csfcheck-pg-"))
    data, sock = root / "data", root / "sock"
    sock.mkdir()
    env = {**os.environ, "LC_ALL": "C"}
    run = dict(check=True, capture_output=True, env=env)
    try:
        subprocess.run([bindir / "initdb", "-D", data, "-U", "csfcheck", "-A", "trust", "-E", "UTF8"], **run)
        opts = f"-k {sock} -p {port} -c listen_addresses='' -c shared_buffers=16MB -c fsync=off"
        subprocess.run([bindir / "pg_ctl", "-D", data, "-o", opts, "-l", root / "pg.log", "-w", "start"], **run)
        try:
            subprocess.run(
                [bindir / "createdb", "-h", sock, "-p", str(port), "-U", "csfcheck", "csfcheck"], **run
            )
            yield f"postgresql+psycopg://csfcheck@/csfcheck?host={sock}&port={port}"
        finally:
            subprocess.run([bindir / "pg_ctl", "-D", data, "-m", "fast", "-w", "stop"], capture_output=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)
