"""Best-effort recovery of pre-raise salaries that were overwritten before salary_records became a history.

For each employee, looks at their oldest saved payslips (salary_payments keeps a snapshot of basic_pay/
allowances/deductions for the month it was run). If that oldest snapshot differs from the salary they
currently have on file, it means they had a raise at some point and their original structure was
overwritten - so this inserts ONE extra row: their earliest-known structure, dated to the first day of
that payslip's month (or their joining date if that is earlier).

This is best-effort, not exact: it only recovers as far back as the oldest saved payslip goes, and
assumes a single earlier structure (it cannot reconstruct multiple in-between raises that all happened
before any payslip was run). It changes nothing for anyone whose oldest payslip already matches their
current salary - there's nothing to recover for them.

Idempotent: running it twice does nothing extra (it checks for an existing row at that date/employee
before inserting). Read-only by default - pass --apply to actually write.

    venv/bin/python -m app.backfill_salary_history            # shows what it WOULD do
    venv/bin/python -m app.backfill_salary_history --apply    # writes it
"""

import argparse
from datetime import date

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.employee import Employee
from app.models.payroll import SalaryPayment, SalaryRecord


def month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def run(apply: bool) -> None:
    engine = create_engine(settings.database_url_sync)
    recovered = 0
    skipped_no_change = 0
    skipped_already_has_row = 0

    with Session(engine) as session, session.begin():
        employees = session.execute(select(Employee)).scalars().all()
        for employee in employees:
            oldest = session.execute(
                select(SalaryPayment)
                .where(SalaryPayment.employee_id == employee.id, SalaryPayment.basic_pay.is_not(None))
                .order_by(SalaryPayment.year, SalaryPayment.month)
                .limit(1)
            ).scalar_one_or_none()
            if oldest is None:
                continue  # no payslip with a snapshot to recover from

            history = session.execute(
                select(SalaryRecord)
                .where(SalaryRecord.employee_id == employee.id)
                .order_by(SalaryRecord.effective_from)
            ).scalars().all()
            if not history:
                continue  # no current salary set either - nothing to compare against

            earliest_on_file = history[0]
            same_structure = (
                float(earliest_on_file.basic_pay) == float(oldest.basic_pay)
                and float(earliest_on_file.allowances) == float(oldest.allowances or 0)
                and float(earliest_on_file.deductions) == float(oldest.deductions or 0)
            )
            if same_structure:
                skipped_no_change += 1
                continue

            recovered_date = max(employee.date_of_joining, month_start(oldest.year, oldest.month))
            if recovered_date >= earliest_on_file.effective_from:
                # The payslip's month starts on or after what's already on file - nothing earlier to add.
                skipped_no_change += 1
                continue
            already_there = session.execute(
                select(SalaryRecord).where(
                    SalaryRecord.employee_id == employee.id, SalaryRecord.effective_from == recovered_date
                )
            ).scalar_one_or_none()
            if already_there is not None:
                skipped_already_has_row += 1
                continue

            print(
                f"{employee.employee_code} {employee.first_name} {employee.last_name}: "
                f"recovering basic {oldest.basic_pay} from {recovered_date} "
                f"(currently earliest on file is {earliest_on_file.basic_pay} from {earliest_on_file.effective_from})"
            )
            if apply:
                session.add(
                    SalaryRecord(
                        employee_id=employee.id,
                        basic_pay=oldest.basic_pay,
                        allowances=oldest.allowances or 0,
                        deductions=oldest.deductions or 0,
                        effective_from=recovered_date,
                    )
                )
            recovered += 1

        if not apply:
            session.rollback()

    print(
        f"\n{'Applied' if apply else 'Would recover'}: {recovered} people. "
        f"Already matched (nothing to recover): {skipped_no_change}. Already had an earlier row: {skipped_already_has_row}."
    )
    if not apply:
        print("This was a dry run - nothing was written. Re-run with --apply to save it.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Actually write the recovered rows (default: dry run)")
    run(apply=parser.parse_args().apply)
