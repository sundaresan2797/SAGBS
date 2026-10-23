import io

import pytest
from httpx import AsyncClient


async def _login(client: AsyncClient, email: str, password: str) -> dict:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _upload(client, headers, type_id, expiry=None, name="paper.pdf"):
    data = {"document_type_id": type_id}
    if expiry:
        data["expiry_date"] = expiry
    return client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (name, io.BytesIO(b"%PDF-1.4 content"), "application/pdf")},
        data=data,
    )


@pytest.mark.asyncio
async def test_everyone_sees_only_active_types_but_managers_see_all(
    client: AsyncClient, admin_user, employee_user, document_types: dict, demo_password: str
):
    admin = await _login(client, admin_user.email, demo_password)
    employee = await _login(client, employee_user.email, demo_password)

    await client.patch(f"/api/v1/document-types/{document_types['OTHER'].id}", json={"is_active": False}, headers=admin)

    dropdown = (await client.get("/api/v1/document-types", headers=employee)).json()["data"]
    assert [t["code"] for t in dropdown] == ["OFFER_LETTER", "EMPLOYMENT_CONTRACT", "ID_PROOF", "RESUME", "CERTIFICATION"]

    everything = (await client.get("/api/v1/document-types/all", headers=admin)).json()["data"]
    assert len(everything) == 6
    assert {t["code"]: t["is_active"] for t in everything}["OTHER"] is False


@pytest.mark.asyncio
async def test_only_admin_and_hr_manage_document_types(
    client: AsyncClient, admin_user, hr_user, employee_user, founder_user, accountant_user, demo_password: str
):
    payload = {"code": "bank_passbook", "name": "Bank Passbook"}
    for user in (employee_user, founder_user, accountant_user):
        headers = await _login(client, user.email, demo_password)
        assert (await client.post("/api/v1/document-types", json=payload, headers=headers)).status_code == 403
        assert (await client.get("/api/v1/document-types/all", headers=headers)).status_code == 403

    hr = await _login(client, hr_user.email, demo_password)
    created = await client.post("/api/v1/document-types", json=payload, headers=hr)
    assert created.status_code == 201, created.text
    assert created.json()["data"]["code"] == "BANK_PASSBOOK"  # codes are stored upper-case

    admin = await _login(client, admin_user.email, demo_password)
    assert (await client.post("/api/v1/document-types", json={"code": "Voter_ID", "name": "Voter ID"}, headers=admin)).status_code == 201

    # Every visible type can be listed by an ordinary employee.
    employee = await _login(client, employee_user.email, demo_password)
    names = {t["name"] for t in (await client.get("/api/v1/document-types", headers=employee)).json()["data"]}
    assert {"Bank Passbook", "Voter ID"} <= names


@pytest.mark.asyncio
async def test_create_and_update_rules(client: AsyncClient, admin_user, document_types: dict, demo_password: str):
    admin = await _login(client, admin_user.email, demo_password)

    duplicate = await client.post("/api/v1/document-types", json={"code": "resume", "name": "Another Resume"}, headers=admin)
    assert duplicate.status_code == 409
    assert duplicate.json()["error_code"] == "DOCUMENT_TYPE_EXISTS"

    for bad in ({"code": "has space", "name": "Bad"}, {"code": "X", "name": "Short code"}, {"code": "FINE", "name": "x"}):
        assert (await client.post("/api/v1/document-types", json=bad, headers=admin)).status_code == 422

    resume_id = document_types["RESUME"].id
    updated = await client.patch(
        f"/api/v1/document-types/{resume_id}",
        json={"name": "Curriculum Vitae", "description": "Latest CV", "requires_expiry": True, "code": "HACKED"},
        headers=admin,
    )
    body = updated.json()["data"]
    assert updated.status_code == 200
    assert (body["name"], body["description"], body["requires_expiry"]) == ("Curriculum Vitae", "Latest CV", True)
    assert body["code"] == "RESUME"  # the code can never change (it is part of stored file names)

    assert (await client.patch("/api/v1/document-types/9999", json={"name": "Nope"}, headers=admin)).status_code == 404


@pytest.mark.asyncio
async def test_upload_follows_the_type_rules(
    client: AsyncClient, admin_user, employee_user, document_types: dict, demo_password: str
):
    admin = await _login(client, admin_user.email, demo_password)
    employee = await _login(client, employee_user.email, demo_password)
    id_proof = document_types["ID_PROOF"].id

    # A type that needs an expiry date rejects an upload without one - and leaves no file behind.
    await client.patch(f"/api/v1/document-types/{id_proof}", json={"requires_expiry": True}, headers=admin)
    missing = await _upload(client, employee, id_proof)
    assert missing.status_code == 422
    assert missing.json()["error_code"] == "EXPIRY_DATE_REQUIRED"
    from app.services.storage_service import storage_service

    assert list(storage_service.base_dir.rglob("*.pdf")) == []

    ok = await _upload(client, employee, id_proof, expiry="2030-01-31")
    assert ok.status_code == 201, ok.text
    stored = ok.json()["data"]
    assert (stored["document_type"], stored["document_type_name"]) == ("ID_PROOF", "ID Proof")

    # A deactivated type can no longer be chosen.
    await client.patch(f"/api/v1/document-types/{id_proof}", json={"is_active": False}, headers=admin)
    inactive = await _upload(client, employee, id_proof, expiry="2030-01-31")
    assert inactive.status_code == 400
    assert inactive.json()["error_code"] == "DOCUMENT_TYPE_INACTIVE"

    assert (await _upload(client, employee, 9999)).status_code == 404


@pytest.mark.asyncio
async def test_new_type_can_be_used_and_names_the_file(
    client: AsyncClient, admin_user, employee_user, document_types: dict, demo_password: str
):
    admin = await _login(client, admin_user.email, demo_password)
    employee = await _login(client, employee_user.email, demo_password)
    created = await client.post("/api/v1/document-types", json={"code": "PAN_CARD", "name": "PAN Card"}, headers=admin)
    type_id = created.json()["data"]["id"]

    upload = await _upload(client, employee, type_id)
    assert upload.status_code == 201, upload.text
    assert upload.json()["data"]["document_type_name"] == "PAN Card"

    from app.services.storage_service import storage_service

    (stored,) = list(storage_service.base_dir.rglob("*.pdf"))
    assert stored.parent.name == "TEST-0001"
    assert stored.name.startswith("PAN_CARD_")

    listing = (await client.get("/api/v1/documents", headers=employee)).json()["data"]
    assert listing[0]["document_type"] == "PAN_CARD"


@pytest.mark.asyncio
async def test_a_type_in_use_cannot_be_deleted_but_an_unused_one_can(
    client: AsyncClient, admin_user, employee_user, document_types: dict, demo_password: str
):
    admin = await _login(client, admin_user.email, demo_password)
    employee = await _login(client, employee_user.email, demo_password)
    assert (await _upload(client, employee, document_types["RESUME"].id)).status_code == 201

    blocked = await client.delete(f"/api/v1/document-types/{document_types['RESUME'].id}", headers=admin)
    assert blocked.status_code == 400
    assert blocked.json()["error_code"] == "DOCUMENT_TYPE_IN_USE"

    deleted = await client.delete(f"/api/v1/document-types/{document_types['CERTIFICATION'].id}", headers=admin)
    assert deleted.status_code == 200
    codes = {t["code"] for t in (await client.get("/api/v1/document-types/all", headers=admin)).json()["data"]}
    assert "CERTIFICATION" not in codes and "RESUME" in codes
    assert (await client.delete("/api/v1/document-types/9999", headers=admin)).status_code == 404


@pytest.mark.asyncio
async def test_management_list_counts_the_documents_using_each_type(
    client: AsyncClient, admin_user, employee_user, document_types: dict, demo_password: str
):
    """The management list says how many uploaded documents use each type (live, not cached), and only there -
    it is what a manager needs before deactivating or deleting one."""
    admin = await _login(client, admin_user.email, demo_password)
    employee = await _login(client, employee_user.email, demo_password)

    def count_for(listing, code):
        return next(t for t in listing if t["code"] == code)["document_count"]

    before = (await client.get("/api/v1/document-types/all", headers=admin)).json()["data"]
    assert count_for(before, "RESUME") == 0

    assert (await _upload(client, employee, document_types["RESUME"].id)).status_code == 201
    assert (await _upload(client, employee, document_types["RESUME"].id, name="second.pdf")).status_code == 201

    after = (await client.get("/api/v1/document-types/all", headers=admin)).json()["data"]
    assert count_for(after, "RESUME") == 2
    assert count_for(after, "ID_PROOF") == 0
