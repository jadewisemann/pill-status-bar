"""Module base class and registry.

A module owns a piece of system state and knows nothing about the UI.  That
split is the whole reason this layer exists: volume is drawn by the pill bar,
the OSD and the control center slider at the same time, so the volume source
cannot belong to any one of them.

Two ways to stay current:

* event-driven -- `poll_interval_ms = None`, and the module pushes via `emit`
  from a callback (audio endpoint callbacks, WinRT session events, ...)
* polled -- set `poll_interval_ms`; `refresh()` runs on a Qt timer

Anything that blocks belongs on a worker thread.  A module that stalls the Qt
event loop freezes the pill, and a frozen pill is worse than a wrong reading.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any, ClassVar

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

logger = logging.getLogger(__name__)


class Module(QObject):
    """Base for every state source."""

    #: Emitted after the module's state changes.  Carries no payload on purpose:
    #: consumers read `state`, so a burst of changes coalesces naturally.
    changed = pyqtSignal()
    #: Non-fatal problems worth showing in the UI (missing permission, no device).
    failed = pyqtSignal(str)
    #: (callback, result) from `run_async`.  Private: it exists only to hop a
    #: worker thread's result back onto the thread that owns this module.
    _async_done = pyqtSignal(object, object)

    name: ClassVar[str] = "module"
    poll_interval_ms: ClassVar[int | None] = None
    #: True once the platform backend is confirmed present.
    available: bool = True

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state: dict[str, Any] = {}
        self._timer: QTimer | None = None
        self._started = False
        self._async_done.connect(self._deliver_async)

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        try:
            self.on_start()
        except Exception as exc:
            self.available = False
            logger.exception("module %s failed to start", self.name)
            self.failed.emit(str(exc))
            return
        if self.poll_interval_ms:
            self._timer = QTimer(self)
            self._timer.setInterval(self.poll_interval_ms)
            self._timer.timeout.connect(self.refresh)
            self._timer.start()
        self.refresh()

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        try:
            self.on_stop()
        except Exception:
            logger.exception("module %s failed to stop cleanly", self.name)

    @property
    def started(self) -> bool:
        return self._started

    # -- state -------------------------------------------------------------

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def update(self, **fields: Any) -> bool:
        """Merge `fields` into the state; emits `changed` only on a real diff."""
        changes = {k: v for k, v in fields.items() if self._state.get(k, _MISSING) != v}
        if not changes:
            return False
        self._state.update(changes)
        self.changed.emit()
        return True

    def refresh(self) -> None:
        """Re-read the source.  Polled modules override this."""

    # -- hooks -------------------------------------------------------------

    def on_start(self) -> None:
        """Acquire devices, register callbacks.  May raise; start() reports it."""

    def on_stop(self) -> None:
        """Release whatever on_start acquired."""

    # -- helpers -----------------------------------------------------------

    def run_async(self, work: Any, done: Any = None) -> None:
        """Run `work()` on the global thread pool, then `done(result)` on the GUI thread.

        Used for anything that talks to the network or to a slow Win32 call.
        """
        QThreadPool.globalInstance().start(_Job(self, work, done))

    def _deliver_async(self, done: Any, result: Any) -> None:
        """Runs on this module's own thread; see `_async_done`."""
        try:
            done(result)
        except Exception:
            logger.exception("async callback in %s failed", self.name)


class _MISSING:  # sentinel; a plain object() would compare equal to nothing
    pass


class _Job(QRunnable):
    """Worker that hops its result back to the module's thread."""

    def __init__(self, module: Module, work: Any, done: Any) -> None:
        super().__init__()
        self._module = module
        self._work = work
        self._done = done
        self._name = module.name  # cached: reading it later may be too late

    def run(self) -> None:
        """Do the work, then hop the result back through a queued signal.

        Both halves are guarded against the module being torn down mid-flight:
        a surface can be closed -- releasing its modules -- while a DDC/CI read
        or a weather fetch is still running, and by the time the worker returns
        the C++ object is gone.  Touching it then raises RuntimeError, which is
        not an error worth reporting; the result simply has nowhere to go.
        """
        try:
            result = self._work()
        except Exception as exc:
            logger.exception("async work in %s failed", self._name)
            message = str(exc)
            self._safely(lambda: self._module.failed.emit(message))
            return
        if self._done is not None:
            self._safely(lambda: self._module._async_done.emit(self._done, result))

    @staticmethod
    def _safely(emit: Any) -> None:
        try:
            emit()
        except RuntimeError:
            logger.debug("dropping an async result: its module was destroyed")


class ModuleRegistry(QObject):
    """Lazily builds modules and keeps them alive while something uses them.

    Reference counted rather than started-all-at-once: no reason to hold a WiFi
    scan handle open when the control center has never been opened.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._factories: dict[str, Any] = {}
        self._instances: dict[str, Module] = {}
        self._refs: dict[str, int] = {}

    def register(self, name: str, factory: Any) -> None:
        self._factories[name] = factory

    def __contains__(self, name: object) -> bool:
        return name in self._factories

    def __iter__(self) -> Iterator[Module]:
        return iter(list(self._instances.values()))

    def get(self, name: str) -> Module:
        """Return the singleton for `name`, creating and starting it on demand."""
        module = self._instances.get(name)
        if module is None:
            factory = self._factories.get(name)
            if factory is None:
                raise KeyError(f"no module registered as {name!r}")
            module = factory()
            module.setParent(self)
            self._instances[name] = module
            module.start()
        self._refs[name] = self._refs.get(name, 0) + 1
        return module

    def release(self, name: str) -> None:
        """Drop a reference; stops the module when the last user lets go."""
        remaining = self._refs.get(name, 0) - 1
        if remaining > 0:
            self._refs[name] = remaining
            return
        self._refs.pop(name, None)
        module = self._instances.pop(name, None)
        if module is not None:
            module.stop()
            module.deleteLater()

    def stop_all(self) -> None:
        for name in list(self._instances):
            module = self._instances.pop(name)
            module.stop()
        self._refs.clear()
