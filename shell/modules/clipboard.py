"""Clipboard history.

Windows has its own clipboard history (Win+V), but it is not readable by third
parties, so history has to be collected here.  Text entries live in a JSON file;
images are written to a cache directory with an LRU cap so a day of screenshots
cannot quietly eat a gigabyte (spec §8 R5).

When Flow Launcher is handling the clipboard this module is never started.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from PyQt6.QtGui import QGuiApplication

from shell.config import cache_dir
from shell.modules.base import Module

logger = logging.getLogger(__name__)

MAX_ENTRIES = 100
MAX_IMAGE_BYTES = 128 * 1024 * 1024  # ~128 MB of cached images, LRU-evicted
MAX_PREVIEW_CHARS = 200


@dataclass
class ClipEntry:
    kind: str  # "text" | "image"
    preview: str
    digest: str
    at: float
    path: str = ""  # images only

    @property
    def age_text(self) -> str:
        seconds = time.time() - self.at
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{int(seconds // 60)}m ago"
        if seconds < 86400:
            return f"{int(seconds // 3600)}h ago"
        return f"{int(seconds // 86400)}d ago"


class ClipboardModule(Module):
    name = "clipboard"
    #: QClipboard.dataChanged is unreliable for clipboards written by other
    #: processes on Windows, so this polls -- cheaply, since an unchanged
    #: clipboard costs one string compare.
    poll_interval_ms = 700

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._entries: list[ClipEntry] = []
        self._last_digest: str = ""
        self._dir = cache_dir() / "cliphist"
        self._index = self._dir / "index.json"

    # -- lifecycle ---------------------------------------------------------

    def on_start(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._load()
        # Seed the digest with whatever is already on the clipboard so starting
        # the shell does not add a duplicate of the current contents.
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            text = clipboard.text()
            if text:
                self._last_digest = _digest(text.encode("utf-8"))

    def on_stop(self) -> None:
        self._save()

    # -- polling -----------------------------------------------------------

    def refresh(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return
        text = clipboard.text()
        if text:
            self._capture_text(text)
            return
        image = clipboard.image()
        if not image.isNull():
            self._capture_image(image)

    def _capture_text(self, text: str) -> None:
        digest = _digest(text.encode("utf-8"))
        if digest == self._last_digest:
            return
        self._last_digest = digest
        preview = text.strip().replace("\n", " ⏎ ")[:MAX_PREVIEW_CHARS]
        self._push(ClipEntry(kind="text", preview=preview, digest=digest, at=time.time()))

    def _capture_image(self, image: object) -> None:
        from PyQt6.QtCore import QBuffer, QByteArray

        buffer_data = QByteArray()
        buffer = QBuffer(buffer_data)
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")  # type: ignore[attr-defined]
        buffer.close()
        payload = bytes(buffer_data)
        digest = _digest(payload)
        if digest == self._last_digest:
            return
        self._last_digest = digest

        path = self._dir / f"{digest}.png"
        try:
            path.write_bytes(payload)
        except OSError as exc:
            logger.error("could not cache clipboard image: %s", exc)
            return
        size = image.size()  # type: ignore[attr-defined]
        self._push(
            ClipEntry(
                kind="image",
                preview=f"image {size.width()}x{size.height()}",
                digest=digest,
                at=time.time(),
                path=str(path),
            )
        )
        self._evict_images()

    # -- history -----------------------------------------------------------

    def _push(self, entry: ClipEntry) -> None:
        self._entries = [e for e in self._entries if e.digest != entry.digest]
        self._entries.insert(0, entry)
        del self._entries[MAX_ENTRIES:]
        self.update(count=len(self._entries))
        self._save()

    @property
    def entries(self) -> list[ClipEntry]:
        return list(self._entries)

    def search(self, query: str) -> list[ClipEntry]:
        if not query:
            return self.entries
        needle = query.lower()
        return [e for e in self._entries if needle in e.preview.lower()]

    def copy(self, digest: str) -> bool:
        """Put an entry back on the clipboard."""
        entry = next((e for e in self._entries if e.digest == digest), None)
        clipboard = QGuiApplication.clipboard()
        if entry is None or clipboard is None:
            return False
        if entry.kind == "image":
            from PyQt6.QtGui import QImage

            image = QImage(entry.path)
            if image.isNull():
                return False
            clipboard.setImage(image)
        else:
            clipboard.setText(entry.preview)
        self._last_digest = entry.digest
        return True

    def remove(self, digest: str) -> None:
        entry = next((e for e in self._entries if e.digest == digest), None)
        if entry is None:
            return
        self._entries.remove(entry)
        if entry.kind == "image" and entry.path:
            Path(entry.path).unlink(missing_ok=True)
        self.update(count=len(self._entries))
        self._save()

    def clear(self) -> None:
        for entry in self._entries:
            if entry.kind == "image" and entry.path:
                Path(entry.path).unlink(missing_ok=True)
        self._entries.clear()
        self.update(count=0)
        self._save()

    # -- persistence -------------------------------------------------------

    def _load(self) -> None:
        if not self._index.is_file():
            return
        try:
            raw = json.loads(self._index.read_text(encoding="utf-8"))
            self._entries = [ClipEntry(**item) for item in raw][:MAX_ENTRIES]
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("clipboard history unreadable (%s); starting empty", exc)
            self._entries = []
        self.update(count=len(self._entries))

    def _save(self) -> None:
        try:
            self._index.write_text(json.dumps([asdict(e) for e in self._entries], indent=0), encoding="utf-8")
        except OSError as exc:
            logger.error("could not save clipboard history: %s", exc)

    def _evict_images(self) -> None:
        """Drop the oldest cached images once the directory passes the cap."""
        images = [e for e in self._entries if e.kind == "image" and e.path]
        total = 0
        for entry in images:
            try:
                total += Path(entry.path).stat().st_size
            except OSError:
                continue
        if total <= MAX_IMAGE_BYTES:
            return
        for entry in reversed(images):  # oldest first
            if total <= MAX_IMAGE_BYTES:
                break
            try:
                total -= Path(entry.path).stat().st_size
                Path(entry.path).unlink(missing_ok=True)
            except OSError:
                pass
            self._entries.remove(entry)
        self.update(count=len(self._entries))
        self._save()


def _digest(payload: bytes) -> str:
    return hashlib.sha1(payload, usedforsecurity=False).hexdigest()[:16]
