"""Virtual desktops as workspaces, via pyvda.

Windows virtual desktops are not Hyprland workspaces: they are created and
destroyed explicitly, they do not renumber themselves, and switching has no
animation hook.  The indicator therefore shows "desktop N of M" rather than
pretending an empty workspace 4 exists (spec §8 R6).
"""

from __future__ import annotations

import logging
from typing import Any

from shell.modules.base import Module
from shell.platform import IS_WINDOWS

logger = logging.getLogger(__name__)


class WorkspacesModule(Module):
    name = "workspaces"
    #: pyvda offers no change notification, so this polls.  Fast enough that a
    #: desktop switch feels instant, slow enough to stay invisible in a profiler.
    poll_interval_ms = 500

    def __init__(self, max_workspaces: int = 5, backend: str = "vd", parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._max = max_workspaces
        self._backend = backend
        self._vda: Any = None

    def on_start(self) -> None:
        if not IS_WINDOWS or self._backend == "none":
            self.available = False
            self.update(count=0, current=0, enabled=False)
            return
        try:
            import pyvda

            self._vda = pyvda
        except ImportError as exc:
            self.available = False
            self.update(count=0, current=0, enabled=False)
            self.failed.emit("pyvda not installed")
            logger.info("virtual desktop support unavailable: %s", exc)
            return
        self.update(enabled=True)

    def refresh(self) -> None:
        if self._vda is None:
            return
        try:
            desktops = self._vda.get_virtual_desktops()
            current = self._vda.VirtualDesktop.current()
            self.update(
                count=min(len(desktops), self._max),
                total=len(desktops),
                current=int(current.number),
            )
        except Exception as exc:
            logger.debug("virtual desktop read failed: %s", exc)

    def switch_to(self, number: int) -> bool:
        """Move to desktop `number` (1-based).  No-op if it does not exist."""
        if self._vda is None:
            return False
        try:
            desktops = self._vda.get_virtual_desktops()
            if not 1 <= number <= len(desktops):
                return False
            self._vda.VirtualDesktop(number).go()
            self.refresh()
            return True
        except Exception as exc:
            logger.error("could not switch desktop: %s", exc)
            return False

    def cycle(self, delta: int) -> bool:
        current = int(self.get("current", 1))
        total = int(self.get("total", 1))
        if total <= 1:
            return False
        target = ((current - 1 + delta) % total) + 1
        return self.switch_to(target)

    def set_max(self, value: int) -> None:
        self._max = value
        self.refresh()
