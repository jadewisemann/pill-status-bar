# ChillPill-Win — implementation spec

Windows port of the ChillPill-Shell *design*. PyQt6 + Win32/WinRT, written from
scratch; yasb is not forked, only its Win32 plumbing is vendored.

Target OS: Windows 10 1809+ / Windows 11.

---

## 0. One-line definition

**A single frameless window that animates its size and corner radius as it
changes state.** That is the whole product.

This is not "a bar with widgets on it". The original's one `box` Rectangle
morphs into the pill bar, the control center, an OSD, a notification and a
launcher. Every design decision below follows from that.

---

## 1. What was ported

### 1.1 The morph table

Transcribed from the original's shell.qml (lines 195–250) and implemented as
data in [`shell/state.py`](../shell/state.py). `ps` = `pillScale`.

| State | width | height | radius |
| --- | --- | --- | --- |
| idle | `row.width + 12·ps + 56·ps` | `row.height·ps + 10` | `20·ps` |
| idle (hover) | `row.width + 12·ps + 68·ps` | ″ | ″ |
| OSD (volume/brightness/battery/timer) | 220 | 40 | 20 |
| notification popup | 305 | 52 | 99 |
| media auto-popup | 340 | 90 | 22 |
| control center (no media) | 390 | `118 + notifBump` | 25 |
| control center (media) | 390 | `240 + notifBump` | 23 |
| app launcher | 390 | 410 | 30 |
| mini dashboard | 420 | 155 | 20 |
| clipboard history | 460 | 270 | 28 |
| wallpaper switcher | 600 | 308 | 30 |

`notifBump = min(list height + 40, 130)`, and exactly `0` when the stack is
empty.

**Animation** — width and radius: `OutExpo`, 225 ms. Height: `OutExpo`, 550 ms,
except the media auto-popup at 650 ms.

**Background** — media popup `#151515`, control-center-with-media `#1a1a1a`,
everything else `#171717`.

**Exclusivity** — control center, dashboard, clipboard, launcher and wallpaper
switcher are mutually exclusive; opening one closes the others.

**Priority** — an open panel outranks every transient overlay, then
notification > OSD > media popup > idle. (The original's ordering is implicit
in QML binding order; this is the reading that matches the behaviour, and it is
asserted in `tests/test_state.py`.)

### 1.2 Palette

| Role | Value |
| --- | --- |
| background | `#171717` |
| background (media popup) | `#151515` |
| background (control center + media) | `#1a1a1a` |
| text | `#dadada` |
| muted text | `#979797` |
| battery > 30% or charging | `#4bd25c` |
| battery 16–30% | `#eecc47` |
| battery ≤ 15% | `#e22323` |

Surfaces, borders and slider chrome are derived from these in
[`shell/theme.py`](../shell/theme.py) and marked as such.

### 1.3 Configuration

24 keys from the original, ported; three added for Windows. Flat JSONC at
`%APPDATA%\chillpill-win\config.jsonc`, one pydantic model, no schema system.
See [`shell/config.py`](../shell/config.py) — the table of ports is in
[README.md](../README.md#configuration).

---

## 2. Platform mapping

| Feature | ChillPill (Linux) | ChillPill-Win |
| --- | --- | --- |
| always on top, no focus steal | layer-shell | `WS_EX_TOOLWINDOW \| WS_EX_NOACTIVATE` + `SetWindowPos(HWND_TOPMOST)` |
| reserved work area | `exclusiveZone` | `SHAppBarMessage` |
| input mask | `mask: Region` | `SetWindowRgn` with a round-rect region |
| blur | compositor | `DwmSetWindowAttribute` + `SetWindowCompositionAttribute` |
| keyboard focus | `WlrKeyboardFocus.Exclusive` | drop `WS_EX_NOACTIVATE` + `AttachThreadInput` foreground dance |
| workspaces | Hyprland IPC | virtual desktops via `pyvda` |
| volume | PipeWire | `pycaw` / `IAudioEndpointVolume` callbacks |
| brightness | `brightnessctl` | WMI internally, DDC/CI externally |
| battery | UPower | `GetSystemPowerStatus` |
| media | MPRIS | WinRT `GlobalSystemMediaTransportControlsSessionManager` |
| notifications | DBus | WinRT `UserNotificationListener` (needs a permission grant) |
| WiFi | NetworkManager | `wlanapi` |
| bandwidth | `nusgmon` | `GetIfEntry2` deltas |
| clipboard history | `cliphist` | own poller + LRU cache, or Flow |
| wallpaper | `swww` | `SystemParametersInfoW(SPI_SETDESKWALLPAPER)` |
| lock / sleep / power | `hyprlock`, systemd | `LockWorkStation`, `SetSuspendState`, `ExitWindowsEx` |
| IPC | Quickshell `IpcHandler` | named pipe `\\.\pipe\chillpill_ipc` |
| hotkeys | Hyprland binds | `RegisterHotKey` on a message-loop thread |

---

## 3. Architecture

```
config ──► modules ──► surfaces ──► pill (one window)
              │            │
              └──► app ◄───┘   timers · IPC · hotkeys · tray · power
```

**Modules own state and know nothing about the UI.** Volume is drawn by the
pill bar, the OSD and the control center slider simultaneously, so the volume
source cannot belong to any of them. Contract in
[`shell/modules/base.py`](../shell/modules/base.py).

**Surfaces are pages, not windows.** The one exception is the fullscreen toast,
which has to be visible when the pill itself is hidden behind a game.

**No settings-schema system.** One pydantic model.

**`vendor/` is read-only.** Adapters live in `shell/platform/`.

### Implementation notes

* The radius animates, so it is a `pyqtProperty(float)` painted in
  `paintEvent`, not a stylesheet `border-radius`.
* Width and height animate on different durations, so they are two
  `QVariantAnimation`s driving one `setGeometry`, not a geometry animation.
* `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)` runs before
  `QApplication` exists. Skipping it is the usual cause of a mis-scaled pill on
  multi-monitor setups.
* Blocking work goes through `Module.run_async`. A stalled event loop freezes
  the pill, which is worse than a stale reading.

---

## 4. Provenance

Vendored, reference-read and deliberately-excluded code are catalogued in
[NOTICE](../NOTICE) and [vendor/README.md](../vendor/README.md).
Design attribution is in [CREDITS.md](CREDITS.md).

---

## 5. IPC

Newline-framed JSON over `\\.\pipe\chillpill_ipc`, default DACL (current user
only). Grammar in [`shell/ipc/protocol.py`](../shell/ipc/protocol.py), commands
in [README.md](../README.md#command-line).

---

## 6. Flow Launcher

Flow is single-instance and its second-instance handler takes no arguments, so
nothing can open it with a query pre-filled. The workable direction is a plugin
*inside* Flow calling out — see
[integrations/flow_plugin/README.md](../integrations/flow_plugin/README.md).
Optional, never required: the built-in launcher and clipboard surfaces stand on
their own.

---

## 7. Known risks

Tracked with their mitigations in [RISKS.md](RISKS.md).
