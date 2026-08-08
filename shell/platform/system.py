"""Session actions: lock, sleep, reboot, wallpaper, launching things.

Each function returns True when the action was actually dispatched, so the UI
can grey out a button instead of pretending the click worked.
"""

from __future__ import annotations

import ctypes
import logging
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from shell.platform import IS_WINDOWS

logger = logging.getLogger(__name__)

# ExitWindowsEx flags
EWX_LOGOFF = 0x00000000
EWX_SHUTDOWN = 0x00000001
EWX_REBOOT = 0x00000002
EWX_FORCE = 0x00000004
EWX_POWEROFF = 0x00000008
EWX_FORCEIFHUNG = 0x00000010
SHTDN_REASON_MAJOR_OTHER = 0x00000000
SHTDN_REASON_MINOR_OTHER = 0x00000000
SHTDN_REASON_FLAG_PLANNED = 0x80000000

SPI_SETDESKWALLPAPER = 0x0014
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _shutdown_privilege() -> bool:
    """Enable SE_SHUTDOWN_NAME on our own token.

    ExitWindowsEx silently fails without it, and the failure looks exactly like
    the user cancelling, so it is worth doing up front.
    """
    if not IS_WINDOWS:
        return False
    try:
        import win32api
        import win32con
        import win32security

        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32con.TOKEN_ADJUST_PRIVILEGES | win32con.TOKEN_QUERY,
        )
        luid = win32security.LookupPrivilegeValue(None, win32security.SE_SHUTDOWN_NAME)
        win32security.AdjustTokenPrivileges(token, False, [(luid, win32con.SE_PRIVILEGE_ENABLED)])
        return True
    except Exception as exc:
        logger.error("could not acquire shutdown privilege: %s", exc)
        return False


def lock_session(command: str | None = None) -> bool:
    """Lock the workstation.  `command` overrides with the configured command."""
    if not IS_WINDOWS:
        return False
    if command and command.strip() and "LockWorkStation" not in command:
        return run_detached(command)
    try:
        return bool(ctypes.windll.user32.LockWorkStation())  # type: ignore[attr-defined]
    except Exception as exc:
        logger.error("lock failed: %s", exc)
        return False


def suspend(hibernate: bool = False) -> bool:
    """Sleep (or hibernate) the machine."""
    if not IS_WINDOWS:
        return False
    try:
        # SetSuspendState(Hibernate, ForceCritical, DisableWakeEvent)
        return bool(ctypes.windll.powrprof.SetSuspendState(int(hibernate), 0, 0))  # type: ignore[attr-defined]
    except Exception as exc:
        logger.error("suspend failed: %s", exc)
        return False


def _exit_windows(flags: int) -> bool:
    if not IS_WINDOWS:
        return False
    _shutdown_privilege()
    reason = SHTDN_REASON_MAJOR_OTHER | SHTDN_REASON_MINOR_OTHER | SHTDN_REASON_FLAG_PLANNED
    try:
        return bool(ctypes.windll.user32.ExitWindowsEx(flags, reason))  # type: ignore[attr-defined]
    except Exception as exc:
        logger.error("ExitWindowsEx(%#x) failed: %s", flags, exc)
        return False


def log_off() -> bool:
    return _exit_windows(EWX_LOGOFF | EWX_FORCEIFHUNG)


def reboot() -> bool:
    return _exit_windows(EWX_REBOOT | EWX_FORCEIFHUNG)


def shut_down() -> bool:
    return _exit_windows(EWX_SHUTDOWN | EWX_POWEROFF | EWX_FORCEIFHUNG)


def set_wallpaper(path: str | Path) -> bool:
    """Set the desktop wallpaper on the current monitor set."""
    if not IS_WINDOWS:
        return False
    resolved = str(Path(path).resolve())
    if not os.path.isfile(resolved):
        logger.error("wallpaper %s does not exist", resolved)
        return False
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined]
            SPI_SETDESKWALLPAPER, 0, resolved, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
        )
        return bool(ok)
    except Exception as exc:
        logger.error("set wallpaper failed: %s", exc)
        return False


def run_detached(command: str, cwd: str | None = None) -> bool:
    """Start `command` without blocking and without a console window."""
    try:
        subprocess.Popen(command, shell=True, cwd=cwd, creationflags=_NO_WINDOW)
        return True
    except Exception as exc:
        logger.error("could not run %r: %s", command, exc)
        return False


def open_path(target: str | Path) -> bool:
    """Open a file, folder or URL with its default handler."""
    target = str(target)
    if IS_WINDOWS:
        try:
            os.startfile(target)  # type: ignore[attr-defined]
            return True
        except Exception as exc:
            logger.error("could not open %s: %s", target, exc)
            return False
    opener = shutil.which("xdg-open")
    return run_detached(f'{opener} "{target}"') if opener else False


def open_terminal(preferred: str, fallback: str = "powershell.exe") -> bool:
    """Launch the configured terminal, falling back when it is not installed."""
    for candidate in (preferred, fallback):
        if candidate and (shutil.which(candidate) or Path(candidate).is_file()):
            return run_detached(candidate)
    return False


def open_settings(page: str) -> bool:
    """Open a Windows Settings page, e.g. `privacy-notifications` (spec §8 R2)."""
    return open_path(f"ms-settings:{page}")


# --------------------------------------------------------------------------
# Read-only system facts used by the dashboard
# --------------------------------------------------------------------------


def hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "unknown"


def username() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "user"


def uptime_seconds() -> float:
    """Seconds since boot."""
    if IS_WINDOWS:
        try:
            return ctypes.windll.kernel32.GetTickCount64() / 1000.0  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        with open("/proc/uptime", encoding="utf-8") as handle:
            return float(handle.read().split()[0])
    except OSError:
        return time.monotonic()


def format_uptime(seconds: float) -> str:
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def local_ip() -> str:
    """Primary outbound IPv4, found without sending anything.

    Connecting a UDP socket only picks a route; no packets leave the machine.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.2)
            sock.connect(("192.0.2.1", 9))  # TEST-NET-1, guaranteed unroutable
            return str(sock.getsockname()[0])
    except OSError:
        return "0.0.0.0"


def account_picture() -> str | None:
    """Path to the Windows account picture, used when `displayPicture` is absent."""
    if not IS_WINDOWS:
        return None
    base = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "AccountPictures"
    if not base.is_dir():
        return None
    candidates = sorted(base.rglob("*.jpg")) + sorted(base.rglob("*.png"))
    return str(candidates[-1]) if candidates else None
