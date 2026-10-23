"""Bring your first real data in from Excel. Three commands, run in your own terminal:

    python -m app.import_employees template  my_people.xlsx     make a blank file to fill in
    python -m app.import_employees check     my_people.xlsx     check it - changes NOTHING, lists every problem
    python -m app.import_employees load      my_people.xlsx     load it (asks you to confirm first)

`load` is all-or-nothing: either everyone is saved or nobody is. It writes the temporary passwords to a private file
in `private_exports/` - hand each person their own password, then delete that file.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

from app.cli_quiet import quiet

from app.database.session import AsyncSessionLocal, engine
from app.models import Role, User
from app.models.enums import RoleName
from app.services import import_service

EXPORT_FOLDER = Path("private_exports")


def _print_problems(plan: import_service.ImportPlan) -> None:
    for problem in plan.errors:
        print(f"  ERROR    {problem}")
    for problem in plan.warnings:
        print(f"  warning  {problem}")


async def _check(path: Path) -> import_service.ImportPlan:
    async with AsyncSessionLocal() as session:
        return await import_service.build_plan(session, path)


async def _load(path: Path, admin_email: str | None, assume_yes: bool) -> int:
    async with AsyncSessionLocal() as session:
        plan = await import_service.build_plan(session, path)
        print(f"Checked {path.name}:")
        for line in plan.summary():
            print(f"  - {line}")
        _print_problems(plan)
        if not plan.ok:
            print("\nNothing was loaded. Fix the errors above in the Excel file and run the check again.")
            return 1

        query = select(User).join(Role, User.role_id == Role.id).where(Role.name == RoleName.ADMIN.value)
        if admin_email:
            query = query.where(User.email == admin_email.strip().lower())
        admin = (await session.execute(query.order_by(User.id))).scalars().first()
        if admin is None:
            print("\nNo Admin login was found. Run `python -m app.setup_live` first.")
            return 1

        if not assume_yes:
            print(f"\nThis will add {len(plan.people)} employees. Have you taken a backup? (pg_dump ...)")
            if input("Type YES to load them now: ").strip() != "YES":
                print("Cancelled. Nothing was loaded.")
                return 1
        result = await import_service.execute_plan(session, plan, admin)

    sheet = import_service.write_login_sheet(result, EXPORT_FOLDER)
    print(
        f"\nLoaded: {result.employees} employees, {result.departments} departments, {result.job_titles} job titles, "
        f"{result.salaries} salaries, {result.leave_balances} leave balances."
    )
    print(f"Temporary passwords are in: {sheet}")
    print("Give each person only their own email and password. They must change it at first sign-in.")
    print("DELETE that file once everyone has been told.")
    return 0


async def main(argv: list[str]) -> int:
    quiet()
    parser = argparse.ArgumentParser(prog="python -m app.import_employees", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("template", help="write a blank Excel file to fill in").add_argument("file")
    sub.add_parser("check", help="check a filled file (changes nothing)").add_argument("file")
    load = sub.add_parser("load", help="load a checked file into the system")
    load.add_argument("file")
    load.add_argument("--admin", help="the Admin's email (default: the first Admin)")
    load.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args(argv)
    path = Path(args.file)

    try:
        if args.command == "template":
            if path.exists():
                print(f"{path} already exists. Choose another name so nothing is overwritten.")
                return 1
            import_service.write_template(path)
            print(f"Wrote {path}. Open it in Excel, read the 'Read me first' sheet, and fill in 'People'.")
            return 0
        if not path.is_file():
            print(f"Cannot find {path}.")
            return 1
        if args.command == "check":
            plan = await _check(path)
            for line in plan.summary():
                print(f"  - {line}")
            _print_problems(plan)
            print("\nOK: the file can be loaded." if plan.ok else "\nNot ready: fix the errors above and check again.")
            return 0 if plan.ok else 1
        return await _load(path, args.admin, args.yes)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
