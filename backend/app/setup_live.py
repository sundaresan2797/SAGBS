"""First-time setup of a REAL installation. Run it once, on an empty database, in your own terminal:

    python -m app.setup_live

It creates the basics every installation needs (roles, permissions, leave types, document types) and the first
Admin login, whose password YOU type here - it is never printed, stored anywhere else, or passed to anyone.
It creates no demo data. Everything else (departments, job titles, employees, holidays) is then entered in the
application or brought in from an Excel file (see `python -m app.import_employees`).

It refuses to run if the database already has any login, so it can never damage a system that is in use.
"""

import asyncio
import getpass
import logging
import os
import sys

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli_quiet import quiet
from app.core.password_policy import password_problems
from app.core.security import hash_password
from app.database.session import AsyncSessionLocal, engine
from app.models import Role, User
from app.models.enums import AuditAction, RoleName
from app.seed import seed_document_types, seed_leave_types, seed_roles_and_permissions
from app.services.audit_service import log_action

logger = logging.getLogger("ems.setup")


class SetupError(Exception):
    """A reason setup cannot go ahead, worded for the person running it."""


async def run_setup(session: AsyncSession, admin_email: str, admin_password: str) -> User:
    """Create the basics and the first Admin login. Raises SetupError (and changes nothing) if it should not run."""
    try:
        admin_email = validate_email(admin_email.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as error:
        raise SetupError(f"That email address is not valid: {error}") from None
    problems = password_problems(admin_password, admin_email)
    if problems:
        raise SetupError("That password is too weak. " + " ".join(problems))
    if (await session.execute(select(func.count()).select_from(User))).scalar_one() > 0:
        raise SetupError(
            "This database already has logins, so setup will not run. "
            "It is only for a brand-new, empty database. Nothing was changed."
        )

    roles = await seed_roles_and_permissions(session)
    await seed_leave_types(session)
    await seed_document_types(session)

    admin_role: Role = roles[RoleName.ADMIN.value]
    admin = User(
        email=admin_email,
        hashed_password=hash_password(admin_password),
        role_id=admin_role.id,
        is_active=True,
        must_change_password=False,  # the person setting up the system chose this password just now
    )
    session.add(admin)
    await session.flush()
    await log_action(
        session,
        user_id=admin.id,
        action=AuditAction.SETUP_SYSTEM,
        entity_type="User",
        entity_id=admin.id,
        description=f"First-time setup: created the Admin login {admin_email}, roles, leave types and document types",
        request=None,
    )
    await session.commit()
    return admin


def _ask_password() -> str:
    while True:
        first = getpass.getpass("Choose the Admin password (typing is hidden): ")
        if first != getpass.getpass("Type it again: "):
            print("The two passwords are different. Try again.\n")
            continue
        return first


async def main() -> int:
    quiet()
    email = os.environ.get("EMS_ADMIN_EMAIL") or input("Admin email address (this is the Admin's sign-in): ").strip()
    password = os.environ.get("EMS_ADMIN_PASSWORD") or _ask_password()
    try:
        async with AsyncSessionLocal() as session:
            admin = await run_setup(session, email, password)
    except SetupError as error:
        print(f"\nSetup stopped: {error}")
        return 1
    finally:
        await engine.dispose()

    print(f"\nDone. The Admin can now sign in with {admin.email} and the password you chose.")
    print("Next: sign in, then add departments, job titles and holidays, and bring in your employees")
    print("(see docs/09-clean-start-and-import.md).")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(asyncio.run(main()))
