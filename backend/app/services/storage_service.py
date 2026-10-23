import re
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings
from app.core.exceptions import ValidationAppError
from app.utils.timezone import today_in_org_tz

# Employees may only upload PDFs. The file's name and content-type come from
# the user's browser and can be faked, so the real check is on the content:
# every genuine PDF starts with these bytes.
ALLOWED_EXTENSIONS = {".pdf"}
PDF_SIGNATURE = b"%PDF-"
PDF_MIME_TYPE = "application/pdf"

# Photos: the real format is read from the picture itself (a file called .jpg proves nothing).
PHOTO_FORMATS = {"JPEG", "PNG", "WEBP"}
PHOTO_MAX_PIXELS = 40_000_000  # refuses absurdly large pictures before they are decoded into memory
PHOTO_MIME_TYPE = "image/jpeg"  # every saved photo is a JPEG, whatever was uploaded

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_-]")


def _safe_part(value: str) -> str:
    """Keeps a value usable in a folder or file name: letters, digits, dash, underscore."""
    return _UNSAFE_CHARS.sub("_", value)


class StorageService:
    """Local-disk file storage.

    Files live in one folder per employee, named by employee code
    (uploads/EMP-0003/RESUME_20260920_9f3a.pdf). Nothing the user typed ever
    becomes part of a path - only the server-side employee code, the document
    type, the date and a short random suffix - so a hostile file name can't
    escape the folder. All business logic (validation of who may upload, DB
    records, authorization) stays in the document service, so swapping this for
    an S3/Azure Blob-backed implementation later only requires replacing
    save/read/delete here - callers never change.
    """

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def max_upload_mb(self) -> int:
        return settings.max_upload_size_mb

    @property
    def max_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def _validate(self, file: UploadFile, content: bytes) -> None:
        if Path(file.filename or "").suffix.lower() not in ALLOWED_EXTENSIONS:
            raise ValidationAppError("Only PDF files can be uploaded.", error_code="UNSUPPORTED_FILE_TYPE")
        if not content:
            raise ValidationAppError("This file is empty. Please choose another PDF.", error_code="EMPTY_FILE")
        if len(content) > self.max_bytes:
            raise ValidationAppError(
                f"This file is larger than the {settings.max_upload_size_mb} MB limit. Please choose a smaller PDF.",
                error_code="FILE_TOO_LARGE",
            )
        if not content.startswith(PDF_SIGNATURE):
            raise ValidationAppError(
                "This file doesn't look like a real PDF. Please choose a PDF document.",
                error_code="UNSUPPORTED_FILE_TYPE",
            )

    async def save(self, employee_code: str, document_type: str, file: UploadFile) -> tuple[str, int, str]:
        # Read at most one byte past the limit: enough to know it's too big
        # without pulling a huge upload into memory.
        content = await file.read(self.max_bytes + 1)
        self._validate(file, content)

        folder_name = _safe_part(employee_code)
        employee_dir = self.base_dir / folder_name
        employee_dir.mkdir(parents=True, exist_ok=True)

        stamp = today_in_org_tz().strftime("%Y%m%d")
        while True:
            file_name = f"{_safe_part(document_type)}_{stamp}_{uuid.uuid4().hex[:4]}.pdf"
            try:
                # "x" fails instead of overwriting if two uploads ever pick the same name.
                with open(employee_dir / file_name, "xb") as destination:
                    destination.write(content)
                break
            except FileExistsError:
                continue

        return f"{folder_name}/{file_name}", len(content), PDF_MIME_TYPE

    def process_photo(self, content: bytes) -> bytes:
        """A square JPEG, `photo_size_px` wide: the picture cropped to its centre, turned upright, and stripped of
        everything hidden in it (camera details, GPS location). Raises a plain-language error for anything that
        is not a real JPG, PNG or WebP picture."""
        not_a_picture = ValidationAppError(
            "This doesn't look like a photo. Please choose a JPG, PNG or WebP picture.", error_code="UNSUPPORTED_FILE_TYPE"
        )
        try:
            with Image.open(BytesIO(content)) as picture:
                if picture.format not in PHOTO_FORMATS:
                    raise not_a_picture
                if picture.width * picture.height > PHOTO_MAX_PIXELS:
                    raise ValidationAppError("This picture is too large. Please choose a smaller one.", error_code="PHOTO_TOO_LARGE")
                upright = ImageOps.exif_transpose(picture)
                rgb = upright.convert("RGB")
        except ValidationAppError:
            raise
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
            raise not_a_picture from None

        side = min(rgb.size)
        left, top = (rgb.width - side) // 2, (rgb.height - side) // 2
        square = rgb.crop((left, top, left + side, top + side)).resize(
            (settings.photo_size_px, settings.photo_size_px), Image.Resampling.LANCZOS
        )
        buffer = BytesIO()
        square.save(buffer, "JPEG", quality=85, optimize=True)  # a fresh image with no metadata
        return buffer.getvalue()

    async def save_photo(self, employee_code: str, file: UploadFile) -> str:
        """Validate, process and store an employee's photo. Returns its path relative to the upload folder.
        Each photo gets a new random name, so a changed photo is never mistaken for the old one."""
        max_bytes = settings.photo_max_upload_mb * 1024 * 1024
        content = await file.read(max_bytes + 1)
        if not content:
            raise ValidationAppError("This file is empty. Please choose another picture.", error_code="EMPTY_FILE")
        if len(content) > max_bytes:
            raise ValidationAppError(
                f"This picture is larger than the {settings.photo_max_upload_mb} MB limit. Please choose a smaller one.",
                error_code="FILE_TOO_LARGE",
            )
        processed = self.process_photo(content)

        folder_name = _safe_part(employee_code)
        employee_dir = self.base_dir / folder_name
        employee_dir.mkdir(parents=True, exist_ok=True)
        while True:
            file_name = f"photo_{uuid.uuid4().hex[:8]}.jpg"
            try:
                with open(employee_dir / file_name, "xb") as destination:
                    destination.write(processed)
                break
            except FileExistsError:
                continue
        return f"{folder_name}/{file_name}"

    def resolve_path(self, relative_path: str) -> Path:
        resolved = (self.base_dir / relative_path).resolve()
        if self.base_dir.resolve() not in resolved.parents and resolved != self.base_dir.resolve():
            raise ValidationAppError("Invalid file path.", error_code="INVALID_FILE_PATH")
        return resolved

    def delete(self, relative_path: str) -> None:
        path = self.resolve_path(relative_path)
        if path.exists():
            path.unlink()


storage_service = StorageService(settings.upload_dir)
