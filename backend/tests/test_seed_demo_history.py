"""The demo-data generator must never be able to run on the real database."""

import pytest

from app.seed_demo_history import assert_demo_database, make_pdf, salary_band


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg2://u:p@localhost:5432/employee_management",
        "postgresql+psycopg2://u:p@localhost:5432/employee_management_test",
        "postgresql+psycopg2://u:p@localhost:5432/demo",  # must END in _demo
        "postgresql+psycopg2://u:p@localhost:5432/",
    ],
)
def test_refuses_anything_that_is_not_a_demo_database(url):
    with pytest.raises(SystemExit) as refused:
        assert_demo_database(url)
    assert "not a demo database" in str(refused.value)


def test_allows_a_demo_database():
    assert_demo_database("postgresql+psycopg2://u:p@localhost:5432/ems_demo")


def test_sample_pdf_is_a_real_pdf():
    pdf = make_pdf("Aadhaar Card - Test (Person)", ["Staff ID: EMP-0001"])
    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")
    assert b"xref" in pdf and b"Aadhaar Card - Test" in pdf


def test_salary_bands_follow_the_role():
    assert salary_band("Founder", "FOUNDER")[0] > salary_band("HR Manager", "MANAGER")[1]
    assert salary_band("Senior Accountant", "ACCOUNTANT")[0] > salary_band("Accountant", "ACCOUNTANT")[1] - 20000
    assert salary_band("HR Executive", "HR")[1] < salary_band("Software Engineer", "EMPLOYEE")[1]
