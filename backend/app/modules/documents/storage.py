"""Private local document storage, behind a small replaceable interface."""

import re
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class BinaryReader(Protocol):
    def read(self, size: int = -1) -> bytes: ...


class LocalDocumentStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)

    def new_key(self) -> str:
        return uuid.uuid4().hex

    def _path(self, key: str) -> Path:
        if not _KEY_PATTERN.fullmatch(key):
            raise ValueError("Invalid storage key")
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise ValueError("Invalid storage key")
        return path

    def save(self, key: str, source: BinaryReader) -> None:
        path = self._path(key)
        # x+b is exclusive: even a collision cannot overwrite an existing object.
        with path.open("x+b") as target:
            while chunk := source.read(64 * 1024):
                target.write(chunk)

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        """Only for undoing a save whose database insert failed. Stored documents are never deleted."""
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()
