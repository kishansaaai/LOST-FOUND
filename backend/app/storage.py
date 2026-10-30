"""File storage behind an interface so S3 can replace the local directory later."""
import io
import uuid
from pathlib import Path
from typing import Protocol

from PIL import Image, UnidentifiedImageError

from .config import get_settings

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


class InvalidUpload(ValueError):
    pass


class Storage(Protocol):
    def save_image(self, data: bytes, folder: str = "items") -> str: ...
    def local_path(self, url: str) -> Path: ...


class LocalStorage:
    """Stores validated, re-encoded images under UPLOAD_DIR and serves them at /uploads/..."""

    def __init__(self, base: str | None = None):
        self.base = Path(base or get_settings().upload_dir).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def save_image(self, data: bytes, folder: str = "items") -> str:
        limit = get_settings().max_upload_mb * 1024 * 1024
        if len(data) > limit:
            raise InvalidUpload(f"file larger than {get_settings().max_upload_mb} MB")
        try:
            img = Image.open(io.BytesIO(data))
            fmt = img.format
            img.verify()                         # structural check; does not decode pixels
            img = Image.open(io.BytesIO(data))   # reopen: verify() invalidates the object
        except (UnidentifiedImageError, OSError, SyntaxError) as e:
            raise InvalidUpload("not a valid image") from e
        if fmt not in ALLOWED_FORMATS:
            raise InvalidUpload(f"unsupported image type {fmt}")
        # Re-encode: drops EXIF/GPS metadata and anything appended to the file.
        img = img.convert("RGB")
        img.thumbnail((1600, 1600))
        name = f"{uuid.uuid4().hex}.jpg"
        target = self.base / folder
        target.mkdir(parents=True, exist_ok=True)
        img.save(target / name, "JPEG", quality=88)
        return f"/uploads/{folder}/{name}"

    def local_path(self, url: str) -> Path:
        rel = url.removeprefix("/uploads/")
        path = (self.base / rel).resolve()
        if self.base not in path.parents:        # no path traversal
            raise InvalidUpload("bad path")
        return path


def get_storage() -> Storage:
    return LocalStorage()
