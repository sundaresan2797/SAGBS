"""Backs up the Docker test environment: its database and its uploads volume, plus the same
structured summary weekly_backup.py writes for the real system - row counts, sizes, what changed.

This is deliberately a SEPARATE tool from weekly_backup.py, not a shared one, for a real reason: the
Docker database is not reachable from the host the normal way. A real Postgres server on this Mac
already owns localhost:5432, so a host-side `pg_dump -h localhost` (what weekly_backup.py does) would
silently back up the REAL company database while you thought you were backing up this Docker test
copy. The only safe way to reach Docker's database is from inside the Docker network itself, via
`docker compose exec` - which is what every command here does.

Run manually any time, from anywhere (it cd's to the project root itself), while the containers are
running (`docker compose up -d` first):
    cd backend && source venv/bin/activate && python scripts/docker_backup.py

Writes into DOCKER_BACKUPS/ (NOT WEEKLY_BACKUPS/ - kept separate on purpose, since mixing a tiny
test database's row counts in with the real system's week-over-week comparison would be misleading).
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent.parent  # .../Desktop/Panneer Anna
COMPOSE_DIR = BACKEND_DIR.parent  # .../employee-management-system (where docker-compose.yml lives)
BACKUP_ROOT = PROJECT_ROOT / "DOCKER_BACKUPS"
KEEP_LAST = 8

POSTGRES_USER = "postgres"
POSTGRES_DB = "employee_management"
CONTAINER_UPLOADS_PATH = "/app/uploads_live"  # must match UPLOAD_DIR - see docker-compose.yml's own comment on this

# Same business tables weekly_backup.py reports on, for a like-for-like summary.
REPORTED_TABLES = [
    ("employees", "Employees"),
    ("users", "Login accounts"),
    ("departments", "Departments"),
    ("designations", "Job titles"),
    ("attendance", "Attendance records"),
    ("leave_requests", "Leave requests"),
    ("leave_balances", "Leave balances"),
    ("short_permissions", "Recorded permissions"),
    ("holidays", "Holidays"),
    ("salary_records", "Salary structures"),
    ("salary_payments", "Salary payments"),
    ("expense_claims", "Expense claims"),
    ("tasks", "Tasks"),
    ("task_comments", "Task comments"),
    ("employee_documents", "Uploaded documents"),
    ("notifications", "Notifications"),
    ("audit_logs", "Audit log entries"),
]


def _docker_env() -> dict[str, str]:
    # `docker` isn't always on PATH outside an interactive shell - add its known install location.
    return {**os.environ, "PATH": f"{Path.home() / '.docker' / 'bin'}:{os.environ.get('PATH', '')}"}


def _compose(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["docker", "compose", *args], cwd=COMPOSE_DIR, env=_docker_env(),
        capture_output=capture, text=capture,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() if capture else ""
        raise RuntimeError(
            f"docker compose {' '.join(args)} failed.{(' ' + detail) if detail else ''} "
            "Is the Docker environment running? Try: docker compose up -d"
        )
    return result


def _sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dump_database(out_file: Path) -> None:
    container_path = "/tmp/docker_backup.dump"
    _compose("exec", "-T", "postgres", "pg_dump", "-U", POSTGRES_USER, "-Fc", POSTGRES_DB, "-f", container_path)
    _compose("cp", f"postgres:{container_path}", str(out_file))
    _compose("exec", "-T", "postgres", "rm", container_path)


def _archive_uploads(out_file: Path) -> int:
    container_path = "/tmp/docker_uploads.tar.gz"
    _compose("exec", "-T", "backend", "tar", "czf", container_path, "-C", "/app", CONTAINER_UPLOADS_PATH.rsplit("/", 1)[-1])
    _compose("cp", f"backend:{container_path}", str(out_file))
    _compose("exec", "-T", "backend", "rm", container_path)
    count_result = _compose(
        "exec", "-T", "backend", "sh", "-c", f"find {CONTAINER_UPLOADS_PATH} -type f | wc -l", capture=True,
    )
    return int(count_result.stdout.strip() or 0)


def _table_counts() -> dict[str, int]:
    counts = {}
    for table, _ in REPORTED_TABLES:
        result = _compose(
            "exec", "-T", "postgres", "psql", "-U", POSTGRES_USER, "-d", POSTGRES_DB,
            "-t", "-c", f"SELECT count(*) FROM {table};", capture=True,
        )
        counts[table] = int(result.stdout.strip())
    return counts


def _previous_manifest() -> dict | None:
    if not BACKUP_ROOT.exists():
        return None
    for folder in sorted((p for p in BACKUP_ROOT.iterdir() if p.is_dir()), reverse=True):
        manifest_path = folder / "manifest.json"
        if manifest_path.exists():
            return json.loads(manifest_path.read_text())
    return None


def _prune_old_backups() -> None:
    if not BACKUP_ROOT.exists():
        return
    folders = sorted((p for p in BACKUP_ROOT.iterdir() if p.is_dir()))
    while len(folders) > KEEP_LAST:
        oldest = folders.pop(0)
        shutil.rmtree(oldest)
        print(f"Removed old backup (beyond the last {KEEP_LAST}): {oldest.name}")


def main() -> None:
    try:
        _compose("exec", "-T", "postgres", "true")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    timestamp = datetime.now()
    folder = BACKUP_ROOT / timestamp.strftime("%Y-%m-%d_%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)

    db_file = folder / "database.dump"
    uploads_file = folder / "uploads.tar.gz"

    print(f"Backing up Docker database '{POSTGRES_DB}'...")
    _dump_database(db_file)

    print("Backing up Docker uploads volume...")
    file_count = _archive_uploads(uploads_file)

    print("Counting rows in every table...")
    counts = _table_counts()

    checksums = {"database.dump": _sha256(db_file), "uploads.tar.gz": _sha256(uploads_file)}
    (folder / "CHECKSUMS.txt").write_text("\n".join(f"{h}  {name}" for name, h in checksums.items()) + "\n")

    previous = _previous_manifest()
    previous_counts = previous["table_counts"] if previous else {}

    manifest = {
        "timestamp": timestamp.isoformat(),
        "environment": "docker-test",
        "database_name": POSTGRES_DB,
        "database_dump_bytes": db_file.stat().st_size,
        "uploads_archive_bytes": uploads_file.stat().st_size,
        "uploads_file_count": file_count,
        "table_counts": counts,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))

    lines = [
        f"Docker TEST environment backup - {timestamp.strftime('%A, %d %B %Y, %I:%M %p')}",
        "=" * 60,
        "",
        "This is the Docker test database, NOT your real company data (employee_management_live).",
        f"Database: {POSTGRES_DB}",
        f"Database dump size: {db_file.stat().st_size / 1024:.0f} KB",
        f"Uploads archive size: {uploads_file.stat().st_size / 1024:.0f} KB ({file_count} files)",
        "",
        "What's inside this backup:",
    ]
    for table, label in REPORTED_TABLES:
        count = counts.get(table, 0)
        prev = previous_counts.get(table)
        if prev is not None and prev != count:
            change = count - prev
            lines.append(f"  {label}: {count}  ({'+' if change > 0 else ''}{change} since last backup)")
        else:
            lines.append(f"  {label}: {count}")
    lines += ["", f"Kept: the last {KEEP_LAST} Docker backups (older ones are removed automatically)."]
    (folder / "SUMMARY.txt").write_text("\n".join(lines) + "\n")

    _prune_old_backups()

    print(f"\nDone. Backup saved to {folder}\n")
    print((folder / "SUMMARY.txt").read_text())


if __name__ == "__main__":
    main()
