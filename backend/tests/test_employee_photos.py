"""Employee photos: who may set them, that only real pictures are accepted, that what is saved is a small clean
square, and that the database, the file on disk, the audit log and the notifications all agree."""

import os
from io import BytesIO
from pathlib import Path

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.notification import Notification
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository
from app.services.storage_service import storage_service


async def _login(client: AsyncClient, user: User, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _picture(fmt="JPEG", size=(800, 600), color=(200, 30, 30), **save_kwargs) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, fmt, **save_kwargs)
    return buffer.getvalue()


def _put(client, employee_id, headers, content: bytes, name="me.jpg", mime="image/jpeg"):
    return client.put(f"/api/v1/employees/{employee_id}/photo", files={"file": (name, content, mime)}, headers=headers)


def _photo_files(tmp: Path) -> list[Path]:
    return [p for p in tmp.rglob("photo_*.jpg")]


@pytest.mark.asyncio
async def test_an_employee_sets_their_own_photo_and_everything_agrees(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str, tmp_path
):
    report, report_user = manager_with_team["report_employee"], manager_with_team["report_user"]
    headers = await _login(client, report_user, demo_password)

    response = await _put(client, report.id, headers, _picture())
    assert response.status_code == 200, response.text
    version = response.json()["data"]["photo_version"]
    assert version and len(version) == 8

    # the database points at exactly one file, and that file exists
    await db_session.refresh(report)
    assert report.profile_photo == f"TEST-0002/photo_{version}.jpg"
    assert [p.name for p in _photo_files(tmp_path)] == [f"photo_{version}.jpg"]

    # what comes back is a small clean 400x400 JPEG
    fetched = await client.get(f"/api/v1/employees/{report.id}/photo", headers=headers)
    assert fetched.status_code == 200 and fetched.headers["content-type"] == "image/jpeg"
    assert "private" in fetched.headers["cache-control"]
    image = Image.open(BytesIO(fetched.content))
    assert image.format == "JPEG" and image.size == (400, 400)

    # one audit entry, and no notification (you changed your own)
    audit = (await db_session.execute(select(AuditLog).where(AuditLog.action == "UPDATE_EMPLOYEE_PHOTO"))).scalars().all()
    assert len(audit) == 1 and "own" in audit[0].description and "TEST-0002" in audit[0].description
    assert (await db_session.execute(select(Notification).where(Notification.user_id == report_user.id))).scalars().all() == []


@pytest.mark.asyncio
async def test_the_picture_is_cropped_to_the_centre_and_stripped_of_hidden_data(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    report = manager_with_team["report_employee"]
    headers = await _login(client, manager_with_team["report_user"], demo_password)

    # 800x400: left half red, right half blue, with a GPS block hidden inside
    wide = Image.new("RGB", (800, 400), (255, 0, 0))
    wide.paste((0, 0, 255), (400, 0, 800, 400))
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (12.0, 58.0, 0.0)}  # GPS info
    exif[0x010F] = "SecretCameraMaker"
    buffer = BytesIO()
    wide.save(buffer, "JPEG", exif=exif, quality=95)
    assert Image.open(BytesIO(buffer.getvalue())).getexif().get(0x010F) == "SecretCameraMaker"

    assert (await _put(client, report.id, headers, buffer.getvalue())).status_code == 200
    saved = Image.open(BytesIO((await client.get(f"/api/v1/employees/{report.id}/photo", headers=headers)).content))
    assert saved.size == (400, 400)
    # centre 400x400 of the 800 wide picture = x 200..600: red on the left half, blue on the right half
    left, right = saved.getpixel((20, 200)), saved.getpixel((380, 200))
    assert left[0] > 200 and left[2] < 60 and right[2] > 200 and right[0] < 60
    assert len(saved.getexif()) == 0  # camera details and location are gone


@pytest.mark.asyncio
async def test_png_and_webp_are_accepted_and_all_saved_as_jpeg(
    client: AsyncClient, manager_with_team: dict, demo_password: str
):
    report = manager_with_team["report_employee"]
    headers = await _login(client, manager_with_team["report_user"], demo_password)
    rgba = BytesIO()
    Image.new("RGBA", (300, 300), (10, 200, 10, 0)).save(rgba, "PNG")  # transparent PNG
    for content, name in ((rgba.getvalue(), "a.png"), (_picture("WEBP"), "b.webp"), (_picture("JPEG", (90, 120)), "c.jpg")):
        response = await _put(client, report.id, headers, content, name=name)
        assert response.status_code == 200, f"{name}: {response.text}"
        fetched = await client.get(f"/api/v1/employees/{report.id}/photo", headers=headers)
        assert Image.open(BytesIO(fetched.content)).size == (400, 400)  # even a small picture ends up 400x400


@pytest.mark.asyncio
async def test_only_real_pictures_are_accepted_and_a_refusal_changes_nothing(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str, tmp_path, monkeypatch
):
    report = manager_with_team["report_employee"]
    headers = await _login(client, manager_with_team["report_user"], demo_password)
    assert (await _put(client, report.id, headers, _picture())).status_code == 200
    await db_session.refresh(report)
    before = report.profile_photo

    gif = BytesIO()
    Image.new("RGB", (50, 50)).save(gif, "GIF")
    bad = {
        "text renamed to .jpg": (b"this is not a picture at all", "x.jpg"),
        "a PDF renamed to .png": (b"%PDF-1.4 fake", "x.png"),
        "a GIF": (gif.getvalue(), "x.gif"),
        "an empty file": (b"", "x.jpg"),
        "a broken jpeg": (_picture()[:200], "x.jpg"),
    }
    for label, (content, name) in bad.items():
        response = await _put(client, report.id, headers, content, name=name)
        assert response.status_code in (400, 422), f"{label}: {response.status_code}"
        assert response.json()["error_code"] in ("UNSUPPORTED_FILE_TYPE", "EMPTY_FILE"), label

    monkeypatch.setattr("app.config.settings.photo_max_upload_mb", 1)
    noisy = Image.frombytes("RGB", (1000, 1000), os.urandom(3_000_000))
    big = BytesIO()
    noisy.save(big, "PNG")
    too_big = await _put(client, report.id, headers, big.getvalue(), name="big.png")
    assert too_big.status_code == 422 and too_big.json()["error_code"] == "FILE_TOO_LARGE"

    # every refusal left the existing photo exactly as it was, and no stray files behind
    await db_session.refresh(report)
    assert report.profile_photo == before
    assert len(_photo_files(tmp_path)) == 1


@pytest.mark.asyncio
async def test_who_may_change_whose_photo(
    client: AsyncClient, db_session, manager_with_team: dict, hr_user: User, admin_user: User, founder_user: User,
    executive_user: User, demo_password: str
):
    report, outsider = manager_with_team["report_employee"], manager_with_team["outsider_employee"]
    picture = _picture()

    # HR, Founder, Admin, and Executive (full Founder parity - document:manage_all) can set anyone's
    for user in (hr_user, founder_user, admin_user, executive_user):
        response = await _put(client, report.id, await _login(client, user, demo_password), picture)
        assert response.status_code == 200, f"{user.email}: {response.text}"

    # ...but a colleague or the person's own manager cannot
    for user in (manager_with_team["outsider_user"], manager_with_team["manager_user"]):
        denied = await _put(client, report.id, await _login(client, user, demo_password), picture)
        assert denied.status_code == 403 and denied.json()["error_code"] == "PHOTO_FORBIDDEN", user.email
        removal = await client.delete(f"/api/v1/employees/{report.id}/photo", headers=await _login(client, user, demo_password))
        assert removal.status_code == 403
    # and nobody can change a photo without signing in
    assert (await client.put(f"/api/v1/employees/{report.id}/photo", files={"file": ("a.jpg", picture, "image/jpeg")})).status_code == 401
    assert (await client.get(f"/api/v1/employees/{report.id}/photo")).status_code == 401
    assert (await client.get("/api/v1/employees/photo-index")).status_code == 401
    missing = await _put(client, 99999, await _login(client, hr_user, demo_password), picture)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_hr_changing_someones_photo_tells_them_and_replacing_deletes_the_old_file(
    client: AsyncClient, db_session, manager_with_team: dict, hr_user: User, demo_password: str, tmp_path
):
    report, report_user = manager_with_team["report_employee"], manager_with_team["report_user"]
    hr = await _login(client, hr_user, demo_password)

    first = (await _put(client, report.id, hr, _picture(color=(0, 0, 0)))).json()["data"]["photo_version"]
    second = (await _put(client, report.id, hr, _picture(color=(255, 255, 255)))).json()["data"]["photo_version"]
    assert first != second
    assert [p.name for p in _photo_files(tmp_path)] == [f"photo_{second}.jpg"]  # the first file is gone

    notes = (await db_session.execute(select(Notification).where(Notification.user_id == report_user.id))).scalars().all()
    assert len(notes) == 2 and all("changed your profile photo" in n.message for n in notes)
    assert (await db_session.execute(select(AuditLog).where(AuditLog.action == "UPDATE_EMPLOYEE_PHOTO"))).scalars().all().__len__() == 2
    # the new picture is the one served
    fetched = Image.open(BytesIO((await client.get(f"/api/v1/employees/{report.id}/photo", headers=hr)).content))
    assert fetched.getpixel((200, 200))[0] > 240


@pytest.mark.asyncio
async def test_removing_a_photo_clears_the_database_and_the_file(
    client: AsyncClient, db_session, manager_with_team: dict, hr_user: User, demo_password: str, tmp_path
):
    report, report_user = manager_with_team["report_employee"], manager_with_team["report_user"]
    own = await _login(client, report_user, demo_password)
    hr = await _login(client, hr_user, demo_password)
    assert (await client.delete(f"/api/v1/employees/{report.id}/photo", headers=own)).status_code == 404  # none yet

    await _put(client, report.id, own, _picture())
    removed = await client.delete(f"/api/v1/employees/{report.id}/photo", headers=hr)
    assert removed.status_code == 200 and removed.json()["data"]["photo_version"] is None
    await db_session.refresh(report)
    assert report.profile_photo is None and _photo_files(tmp_path) == []
    assert (await client.get(f"/api/v1/employees/{report.id}/photo", headers=own)).json()["error_code"] == "NO_PHOTO"
    assert (await client.delete(f"/api/v1/employees/{report.id}/photo", headers=hr)).status_code == 404  # already gone
    assert (await db_session.execute(select(AuditLog).where(AuditLog.action == "REMOVE_EMPLOYEE_PHOTO"))).scalars().all().__len__() == 1
    note = (await db_session.execute(select(Notification).where(Notification.user_id == report_user.id, Notification.title == "Your photo was removed"))).scalar_one()
    assert "removed your profile photo" in note.message


@pytest.mark.asyncio
async def test_the_photo_index_lists_only_people_with_photos_and_their_versions(
    client: AsyncClient, manager_with_team: dict, demo_password: str
):
    report, outsider = manager_with_team["report_employee"], manager_with_team["outsider_employee"]
    outsider_headers = await _login(client, manager_with_team["outsider_user"], demo_password)
    empty = await client.get("/api/v1/employees/photo-index", headers=outsider_headers)
    assert empty.status_code == 200 and empty.json()["data"] == []

    version = (await _put(client, report.id, await _login(client, manager_with_team["report_user"], demo_password), _picture())).json()["data"]["photo_version"]
    index = (await client.get("/api/v1/employees/photo-index", headers=outsider_headers)).json()["data"]  # anyone signed in
    assert index == [{"employee_id": report.id, "photo_version": version}]
    # any signed-in colleague can see the picture itself (it is shown next to the person's name everywhere)
    assert (await client.get(f"/api/v1/employees/{report.id}/photo", headers=outsider_headers)).status_code == 200


@pytest.mark.asyncio
async def test_the_stored_path_cannot_be_used_to_read_other_files(
    client: AsyncClient, db_session, manager_with_team: dict, demo_password: str
):
    """profile_photo is only ever written by the server, but reading also refuses a path that escapes the folder."""
    report = manager_with_team["report_employee"]
    report.profile_photo = "../../etc/passwd"
    await db_session.flush()
    response = await client.get(f"/api/v1/employees/{report.id}/photo", headers=await _login(client, manager_with_team["outsider_user"], demo_password))
    assert response.status_code in (404, 422) and "root:" not in response.text
