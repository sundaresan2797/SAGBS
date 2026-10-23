import io

import pytest
from httpx import AsyncClient


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def _pdf_file(name: str = "resume.pdf"):
    return {"file": (name, io.BytesIO(b"%PDF-1.4 fake content"), "application/pdf")}


@pytest.mark.asyncio
async def test_employee_can_upload_and_download_own_document(
    client: AsyncClient, employee_user, demo_password: str, document_types: dict
):
    token = await _login(client, employee_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    upload_response = await client.post(
        "/api/v1/documents", headers=headers, files=_pdf_file(), data={"document_type_id": document_types["RESUME"].id}
    )
    assert upload_response.status_code == 201, upload_response.text
    document_id = upload_response.json()["data"]["id"]

    download_response = await client.get(f"/api/v1/documents/{document_id}/download", headers=headers)
    assert download_response.status_code == 200
    assert download_response.content == b"%PDF-1.4 fake content"


@pytest.mark.asyncio
async def test_unsupported_file_type_rejected(
    client: AsyncClient, employee_user, demo_password: str, document_types: dict
):
    token = await _login(client, employee_user.email, demo_password)
    response = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("virus.exe", io.BytesIO(b"bad"), "application/octet-stream")},
        data={"document_type_id": document_types["OTHER"].id},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_employee_cannot_access_another_employees_document(
    client: AsyncClient, manager_with_team: dict, demo_password: str, document_types: dict
):
    report_user = manager_with_team["report_user"]
    outsider_user = manager_with_team["outsider_user"]

    report_token = await _login(client, report_user.email, demo_password)
    upload_response = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {report_token}"},
        files=_pdf_file(),
        data={"document_type_id": document_types["ID_PROOF"].id},
    )
    document_id = upload_response.json()["data"]["id"]

    outsider_token = await _login(client, outsider_user.email, demo_password)
    forbidden_response = await client.get(
        f"/api/v1/documents/{document_id}/download", headers={"Authorization": f"Bearer {outsider_token}"}
    )
    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["error_code"] == "DOCUMENT_FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_can_access_any_employees_document(
    client: AsyncClient, admin_user, employee_user, demo_password: str, document_types: dict
):
    employee_token = await _login(client, employee_user.email, demo_password)
    upload_response = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {employee_token}"},
        files=_pdf_file(),
        data={"document_type_id": document_types["OFFER_LETTER"].id},
    )
    document_id = upload_response.json()["data"]["id"]

    admin_token = await _login(client, admin_user.email, demo_password)
    response = await client.get(
        f"/api/v1/documents/{document_id}/download", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_document_removes_it(
    client: AsyncClient, employee_user, demo_password: str, document_types: dict
):
    token = await _login(client, employee_user.email, demo_password)
    headers = {"Authorization": f"Bearer {token}"}

    upload_response = await client.post(
        "/api/v1/documents", headers=headers, files=_pdf_file(), data={"document_type_id": document_types["RESUME"].id}
    )
    document_id = upload_response.json()["data"]["id"]

    delete_response = await client.delete(f"/api/v1/documents/{document_id}", headers=headers)
    assert delete_response.status_code == 200

    download_response = await client.get(f"/api/v1/documents/{document_id}/download", headers=headers)
    assert download_response.status_code == 404


# ---------------------------------------------------------------------------
# Upload rules: PDF only, at most 5 MB, stored in the employee's own folder.
# ---------------------------------------------------------------------------


def _upload(client, headers, content: bytes, document_types: dict, name: str = "file.pdf", content_type: str = "application/pdf", **data):
    return client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (name, io.BytesIO(content), content_type)},
        data={"document_type_id": document_types["RESUME"].id, **data},
    )


@pytest.mark.asyncio
async def test_upload_is_stored_in_the_employee_code_folder_with_a_readable_name(
    client: AsyncClient, employee_user, demo_password: str, document_types: dict
):
    import re

    from app.services.storage_service import storage_service

    headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    response = await _upload(client, headers, b"%PDF-1.4 content", document_types, "my cv (final).pdf")
    assert response.status_code == 201, response.text

    # The employee fixture's code is TEST-0001; the name carries the type and date, never the user's file name.
    listing = (await client.get("/api/v1/documents", headers=headers)).json()["data"]
    assert listing[0]["file_name"] == "my cv (final).pdf"  # the original name is still what the user sees

    stored = [p for p in storage_service.base_dir.rglob("*.pdf")]
    assert len(stored) == 1
    relative = stored[0].relative_to(storage_service.base_dir).as_posix()
    assert re.fullmatch(r"TEST-0001/RESUME_\d{8}_[0-9a-f]{4}\.pdf", relative), relative


@pytest.mark.asyncio
async def test_only_real_pdfs_are_accepted(
    client: AsyncClient, employee_user, demo_password: str, document_types: dict
):
    headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}

    for name, content, content_type in (
        ("photo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "image/png"),
        ("photo.jpg", b"\xff\xd8\xff" + b"0" * 20, "image/jpeg"),
        ("letter.docx", b"PK\x03\x04" + b"0" * 20, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("letter.doc", b"\xd0\xcf\x11\xe0" + b"0" * 20, "application/msword"),
    ):
        response = await _upload(client, headers, content, document_types, name, content_type)
        assert response.status_code == 422, name
        assert response.json()["error_code"] == "UNSUPPORTED_FILE_TYPE", name

    # A program (or anything else) merely renamed to .pdf is caught by its content, not its name.
    disguised = await _upload(client, headers, b"MZ\x90\x00 this is really an exe", document_types, "invoice.pdf")
    assert disguised.status_code == 422
    assert disguised.json()["error_code"] == "UNSUPPORTED_FILE_TYPE"

    empty = await _upload(client, headers, b"", document_types, "empty.pdf")
    assert empty.status_code == 422
    assert empty.json()["error_code"] == "EMPTY_FILE"

    assert (await client.get("/api/v1/documents", headers=headers)).json()["data"] == []


@pytest.mark.asyncio
async def test_upload_limit_is_5_mb_exactly(
    client: AsyncClient, employee_user, demo_password: str, document_types: dict
):
    from app.config import settings

    assert settings.max_upload_size_mb == 5
    limit = settings.max_upload_size_mb * 1024 * 1024
    headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}

    at_limit = await _upload(client, headers, b"%PDF-" + b"0" * (limit - 5), document_types)
    assert at_limit.status_code == 201, at_limit.text

    over_limit = await _upload(client, headers, b"%PDF-" + b"0" * (limit - 4), document_types)  # one byte too many
    assert over_limit.status_code == 422
    assert over_limit.json()["error_code"] == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_upload_policy_reports_the_real_enforced_limit(client: AsyncClient, employee_user, demo_password: str):
    """The Add-a-document screen fetches this instead of hardcoding a number, so it can never
    state a limit the server doesn't actually enforce (see test_upload_limit_is_5_mb_exactly)."""
    from app.config import settings

    headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    response = await client.get("/api/v1/documents/policy", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["max_upload_mb"] == settings.max_upload_size_mb
    assert data["allowed_extensions"] == [".pdf"]


@pytest.mark.asyncio
async def test_expiring_documents_lists_expired_and_soon_for_current_staff_only(
    client: AsyncClient, db_session, hr_employee_user, employee_user, demo_password: str, document_types: dict
):
    """The company-wide "Documents to renew" list: already-expired and expiring-within-N-days papers of
    current staff, soonest first. Far-off, undated and ex-employees' documents are left out, and only people
    who can open other people's documents (document:manage_all) may ask."""
    from datetime import date, timedelta

    from sqlalchemy import update

    from app.models.document import EmployeeDocument
    from app.models.employee import Employee
    from app.models.enums import EmployeeStatus
    from app.repositories.employee_repository import EmployeeRepository

    employee = await EmployeeRepository(db_session).get_by_user_id(employee_user.id)
    today = date.today()
    doc_type = next(iter(document_types.values()))

    def add(expiry, name):
        db_session.add(EmployeeDocument(
            employee_id=employee.id, document_type_id=doc_type.id, file_name=name, file_path=f"x/{name}",
            file_size=1, mime_type="application/pdf", expiry_date=expiry, uploaded_by=employee.user_id,
        ))

    add(today - timedelta(days=5), "expired.pdf")
    add(today + timedelta(days=10), "soon.pdf")
    add(today + timedelta(days=200), "far.pdf")
    add(None, "undated.pdf")
    await db_session.flush()

    hr_headers = {"Authorization": f"Bearer {await _login(client, hr_employee_user.email, demo_password)}"}
    response = await client.get("/api/v1/documents/expiring", params={"within_days": 30}, headers=hr_headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 2
    assert [d["file_name"] for d in data["items"]] == ["expired.pdf", "soon.pdf"]
    assert [d["days_left"] for d in data["items"]] == [-5, 10]

    # A wider window picks up the far one too.
    wide = (await client.get("/api/v1/documents/expiring", params={"within_days": 365}, headers=hr_headers)).json()["data"]
    assert wide["total"] == 3

    # Someone who left is no longer anyone's to-do.
    await db_session.execute(update(Employee).where(Employee.id == employee.id).values(status=EmployeeStatus.TERMINATED))
    await db_session.flush()
    gone = (await client.get("/api/v1/documents/expiring", params={"within_days": 30}, headers=hr_headers)).json()["data"]
    assert gone["total"] == 0

    # An ordinary employee can't see the company-wide list.
    employee_headers = {"Authorization": f"Bearer {await _login(client, employee_user.email, demo_password)}"}
    assert (await client.get("/api/v1/documents/expiring", headers=employee_headers)).status_code == 403
