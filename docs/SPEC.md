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

**Animation** — the box: width and radius `OutExpo` 225 ms, height `OutExpo`
550 ms (650 ms for the media auto-popup). But the box is only half of it; the
*content* animates too, and skipping that is what makes a morph read as a
resize. Full table in [`shell/anim.py`](../shell/anim.py):

| What | Timing |
| --- | --- |
| pill bar content | fade, 100 ms |
| panel content (control center, launcher, clipboard, wallpapers) | 15 ms beat, then 150 ms `OutExpo` |
| dashboard content | 1 ms beat, then 300 ms `OutExpo` |
| notification popup / media popup | 150 ms / 180 ms |
| slider fill | 60 ms |
| workspace chip colour | 120 ms |
| toggle colour / press scale | 150 ms / 80 ms `OutQuad` |
| hover colours | 100 ms |
| volume icon, on glyph change | pulse to 1.15× over 60 ms, back over 100 ms |

The 15 ms beat before a panel appears is the load-bearing detail: the box is
already growing when its content starts arriving, so the two movements read as
one. Outgoing and incoming surfaces are cross-faded, never swapped.

`python tools/filmstrip.py idle controlCenter out/morph.png` samples a real
morph every 40 ms and lays the frames out side by side, so the timing can be
inspected without a Windows machine.

**Background** — media popup `#151515`, control-center-with-media `#1a1a1a`,
everything else `#171717`.

**Exclusivity** — control center, dashboard, clipboard, launcher and wallpaper
switcher are mutually exclusive; opening one closes the others.

**Priority** — an open panel outranks every transient overlay, then
notification > OSD > media popup > idle. (The original's ordering is implicit
in QML binding order; this is the reading that matches the behaviour, and it is
asserted in `tests/test_state.py`.)

### 1.2 Palette

From the original's `qml/Theme.qml`:

| Name | Value | Used for |
| --- | --- | --- |
| `bg` | `#171717` | the pill, in every state but the two below |
| `bg1` | `#151515` | media auto-popup; control-center buttons when off |
| `fg` | `#dadada` | body text |
| `fg1` / `fg2` | `#e7e7e7` / `#dfdfdf` | brighter text |
| `fg3d` / `fg4d` | `#a7a7a7` / `#c5c4c4` | dimmer text |
| `accent` | `#979797` | secondary text — a grey, not a highlight |
| `coverArtGlowShadow` | `#80aae6` | album art glow |

Plus the literals its components use inline — battery thresholds
(`#4bd25c` / `#eecc47` / `#e22323`), the WiFi blue `#6791dc`, workspace chips
(`#4d5258` active, `#393c41` occupied), control-center buttons (`#151515` off,
`#212529` on, `#a8a8a8` label), sliders (`#3a3a3a` track, `#c9c9c9` fill), and
the media card at `#1a1a1a` with a 2px `#202020` border.

All of it is in [`shell/theme.py`](../shell/theme.py) and pinned by
[`tests/test_theme.py`](../tests/test_theme.py).

**Fonts** — Monocraft for text, JetBrainsMono Nerd Font Propo for glyphs. The
pill bar's text is 10px × `pillScale`; the panels use fixed sizes because their
boxes are fixed. Padding scales sub-linearly: `1 + (pillScale - 1) * 0.6`.

**Glyphs** — a ten-step battery ramp with the charging bolt *appended* to the
level glyph, four WiFi signal tiers, four brightness steps, and Weather Icons
(not Material Design) for the forecast. Codepoints and names are in
`shell/theme.py`.

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
