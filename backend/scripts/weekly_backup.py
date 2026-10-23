"""Weekly full backup: the database and the uploads folder, plus a structured summary of exactly
what's inside - not just a blind binary file.

Run manually any time:
    cd backend && source venv/bin/activate && python scripts/weekly_backup.py

Scheduled every Friday via cron (see the README note this script prints when run with --cron-line).

Each run creates its own dated folder under WEEKLY_BACKUPS/, fully self-contained - no backup
depends on any other, so any single week's folder can restore the whole system on its own. Only
the last KEEP_LAST folders are kept; older ones are removed automatically.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import get_settings  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent.parent  # .../Desktop/Panneer Anna - alongside DB_BACKUPS, FULL_BACKUP_*
BACKUP_ROOT = PROJECT_ROOT / "WEEKLY_BACKUPS"
KEEP_LAST = 8  # about 2 months of weekly backups

# Business tables worth reporting on, in a friendly order. Plumbing tables (roles, permissions,
# role_permissions, password_reset_tokens, alembic_version) are left out - they don't tell anyone
# anything about how much real company data is in this backup.
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


def _db_params() -> dict[str, str]:
    url = urlparse(get_settings().database_url.replace("+asyncpg", ""))
    return {
        "host": url.hostname or "localhost",
        "port": str(url.port or 5432),
        "user": url.username or "",
        "password": url.password or "",
        "dbname": (url.path or "/").lstrip("/"),
    }


def _pg_env(params: dict[str, str]) -> dict[str, str]:
    return {**os.environ, "PGPASSWORD": params["password"]}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dump_database(params: dict[str, str], out_file: Path) -> None:
    subprocess.run(
        [
            "pg_dump", "-h", params["host"], "-p", params["port"], "-U", params["user"],
            "-Fc", "-f", str(out_file), params["dbname"],
        ],
        check=True, env=_pg_env(params),
    )


def _archive_uploads(upload_dir: Path, out_file: Path) -> int:
    file_count = sum(1 for item in upload_dir.rglob("*") if item.is_file()) if upload_dir.exists() else 0
    with tarfile.open(out_file, "w:gz") as tar:
        if upload_dir.exists():
            tar.add(upload_dir, arcname=upload_dir.name)
    return file_count


def _table_counts(params: dict[str, str]) -> dict[str, int]:
    counts = {}
    for table, _ in REPORTED_TABLES:
        result = subprocess.run(
            [
                "psql", "-h", params["host"], "-p", params["port"], "-U", params["user"],
                "-d", params["dbname"], "-t", "-c", f"SELECT count(*) FROM {table};",
            ],
            check=True, capture_output=True, text=True, env=_pg_env(params),
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
    if "--cron-line" in sys.argv:
        venv_python = BACKEND_DIR / "venv" / "bin" / "python"
        print("Add this line with `crontab -e` to run every Friday at 2 AM:\n")
        print(f"0 2 * * 5 cd {BACKEND_DIR} && {venv_python} scripts/weekly_backup.py >> {PROJECT_ROOT / 'weekly_backup.log'} 2>&1")
        return

    settings = get_settings()
    params = _db_params()
    timestamp = datetime.now()
    folder = BACKUP_ROOT / timestamp.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)

    db_file = folder / "database.dump"
    uploads_file = folder / "uploads.tar.gz"
    upload_dir = (BACKEND_DIR / settings.upload_dir).resolve()

    print(f"Backing up database '{params['dbname']}'...")
    _dump_database(params, db_file)

    print(f"Backing up uploads from {upload_dir}...")
    file_count = _archive_uploads(upload_dir, uploads_file)

    print("Counting rows in every table...")
    counts = _table_counts(params)

    checksums = {"database.dump": _sha256(db_file), "uploads.tar.gz": _sha256(uploads_file)}
    (folder / "CHECKSUMS.txt").write_text("\n".join(f"{h}  {name}" for name, h in checksums.items()) + "\n")

    previous = _previous_manifest()
    previous_counts = previous["table_counts"] if previous else {}

    manifest = {
        "timestamp": timestamp.isoformat(),
        "database_name": params["dbname"],
        "database_dump_bytes": db_file.stat().st_size,
        "uploads_archive_bytes": uploads_file.stat().st_size,
        "uploads_file_count": file_count,
        "table_counts": counts,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))

    lines = [
        f"Weekly backup - {timestamp.strftime('%A, %d %B %Y, %I:%M %p')}",
        "=" * 50,
        "",
        f"Database: {params['dbname']}",
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
    lines += ["", f"Kept: the last {KEEP_LAST} weekly backups (older ones are removed automatically)."]
    (folder / "SUMMARY.txt").write_text("\n".join(lines) + "\n")

    _prune_old_backups()

    print(f"\nDone. Backup saved to {folder}\n")
    print((folder / "SUMMARY.txt").read_text())


if __name__ == "__main__":
    main()
