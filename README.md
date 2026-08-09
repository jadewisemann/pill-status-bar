# ChillPill-Win

A morphing pill shell for Windows.

One frameless window sits at the top of the screen showing the time, battery,
volume and network. Press a key and it *becomes* something else — the control
center, a launcher, a dashboard, a notification — animating its width, height
and corner radius on the way. There is no second window and no widget grid:
the whole shell is one shape that changes.

Design inspired by [ChillPill-Shell](https://github.com/LUCKYS1NGHH/ChillPill-Shell)
by LUCKYS1NGHH, rewritten from scratch for Windows in PyQt6 + Win32/WinRT. No
ChillPill-Shell code or assets are used — see [docs/CREDITS.md](docs/CREDITS.md).

**Status:** the code is complete and the pure layers are tested, but it has not
yet been run on Windows hardware. [docs/RISKS.md](docs/RISKS.md#unverified-on-real-hardware)
lists what that leaves unverified.

---

## The shapes

Every state's exact size comes from one table in
[`shell/state.py`](shell/state.py); nothing else in the codebase hard-codes
geometry.

| State | Size | Radius |
| --- | --- | --- |
| pill bar (idle) | fits its contents | 20 |
| OSD | 220 × 40 | 20 |
| notification | 305 × 52 | 99 |
| media popup | 340 × 90 | 22 |
| control center | 390 × 118 – 370 | 25 / 23 |
| launcher | 390 × 410 | 30 |
| dashboard | 420 × 155 | 20 |
| clipboard history | 460 × 270 | 28 |
| wallpapers | 600 × 308 | 30 |

Width and radius ease over 225 ms; height takes 550 ms, so the pill widens
before it grows. Both curves are `OutExpo`.

Nothing in the pill changes instantly. The box eases, and so does everything
inside it — content cross-fades between surfaces with a 15 ms beat so the box
is already moving when the new content arrives, slider fills ease over 60 ms,
workspace chips over 120 ms, and the volume icon pulses when its glyph changes.
The full timing table is in [`shell/anim.py`](shell/anim.py).

```
python tools/preview.py out/                              # every state, to PNG
python tools/filmstrip.py idle controlCenter out/m.png    # a morph, frame by frame
```

Both run anywhere — no Windows needed.

---

## Requirements

* Windows 10 1809+ or Windows 11 (Mica and rounded corners need 11)
* Python 3.12+ — a vendored file uses PEP 695 syntax
* A Nerd Font for the glyphs; the default is *JetBrainsMono Nerd Font Propo*
* [Monocraft](https://github.com/IdreesInc/Monocraft) for text, or set
  `textFontFamily` to whatever you have

## Install

```
git clone https://github.com/jadewisemann/pill-status-bar
cd pill-status-bar
pip install -e .
python -m shell.doctor      # check the machine before starting anything
python main.py
```

`shell.doctor` lists every backend and says which feature each missing one
costs you. Only two things are blockers — Python 3.12+ and Windows 1809+;
everything else degrades one feature and says so:

```
[+] Python 3.12+      running 3.12.4
[+] Windows           build 22631 (Windows 11: Mica and rounded corners available)
[+] pycaw             volume slider and mute
[~] WMI               internal display brightness unavailable
[~] font: Monocraft   not installed; Qt will substitute and glyphs may show as boxes
```

The first run writes a commented `%APPDATA%\chillpill-win\config.jsonc`. Saving
that file reloads the shell live — no restart.

### What to expect the first time

This has never been run on Windows. Treat the first launch as a debugging
session, not an install:

* run `python main.py` from a terminal so you can see the log
* if it dies, the traceback names the module — every backend is isolated behind
  `shell/modules/` or `shell/platform/`, so one broken backend is one file
* the desktop work area is the thing worth watching. If the shell is killed
  before `quit()` runs, the AppBar reservation can outlive it and leave a strip
  of desktop unusable. Starting the shell again and quitting it cleanly from
  the tray releases it; so does signing out.

---

## Keys

Registered globally at startup; a key another app already owns is skipped with
a log line rather than failing the rest.

| | |
| --- | --- |
| `Win+C` | control center |
| `Win+D` | dashboard |
| `Win+V` | clipboard history |
| `Win+Space` | launcher |
| `Win+W` | wallpapers |
| `Win+Shift+N` | do not disturb |
| `Win+Esc` | close everything |

Clicking the pill bar opens the control center; right-clicking opens the
dashboard; scrolling on it changes volume.

---

## Command line

`chillpillc` writes one JSON line to `\\.\pipe\chillpill_ipc`. Anything the
keys do is scriptable.

```
chillpillc toggle controlCenter
chillpillc show dashboard
chillpillc hide *
chillpillc volume 40
chillpillc volume +5
chillpillc brightness -10
chillpillc timer 10
chillpillc timer cancel
chillpillc dnd on
chillpillc wallpaper C:\Users\me\Pictures\wallpapers\a.png
chillpillc notify "Build finished" "in 42 seconds"
chillpillc status
```

The original shell's target names (`cliphist`, `miniDashboard`, `appLauncher`,
`wallpaperSwitcher`) still work, so scripts written against it keep running.

---

## Configuration

Flat JSONC, comments and trailing commas allowed. Every key from the original
plus three for Windows.

| Key | Default | Notes |
| --- | --- | --- |
| `displayPicture` | `%USERPROFILE%\.pfp.png` | falls back to your Windows account picture |
| `clockFormat` | `hh:mm` | Qt `QTime` format |
| `pillTopMargin` / `pillBottomMargin` | `9` / `26` | also sets the AppBar reservation |
| `pillScale` | `1.0` | multiplies the idle metrics, not the panels |
| `textFontFamily` | `Monocraft` | |
| `nerdFontFamily` | `JetBrainsMono Nerd Font Propo` | |
| `timerPresets` | `[1, 5, 10, 15, 30]` | minutes |
| `mediaPopupDuration` | `2000` | ms; `0` disables the auto-popup |
| `maxWorkspaces` | `5` | virtual desktops shown |
| `notificationDisplayTime` | `3000` | ms |
| `maxNotificationsInStack` | `20` | |
| `avoidDuplicateNotifications` | `true` | |
| `bandwidthRefreshInterval` | `300000` | ms |
| `screenLockAppCommand` | `rundll32.exe user32.dll,LockWorkStation` | |
| `osdDuration` | `800` | ms |
| `weatherLocation` / `weatherUnits` / `weatherRefreshInterval` | `Delhi` / `metric` / `3600000` | Open-Meteo, no key needed |
| `defaultTerminal` | `wt.exe` | falls back to `powershell.exe` |
| `wallpapersDir` | `%USERPROFILE%\Pictures\wallpapers` | |
| `wsCloseOnWallpaperSet` | `true` | |
| **`osdEnabled`** | **`false`** | Windows shows its own volume overlay — see [R1](docs/RISKS.md) |
| **`launcherBackend`** | `auto` | `auto` \| `builtin` \| `flow` |
| **`workspaceBackend`** | `vd` | `vd` \| `none` |

A broken config never stops the shell from starting: it logs what is wrong and
falls back to defaults, because a config typo should not leave you with no UI
to fix it in.

---

## Notifications need permission

Windows will not hand notifications to a third-party app until you allow it:
**Settings → Privacy & security → Notifications → let apps access
notifications**. Until then the shell runs normally with an empty stack and
shows a tray balloon pointing at that page. See
[R2 and R3](docs/RISKS.md).

## Flow Launcher (optional)

If [Flow Launcher](https://www.flowlauncher.com/) is installed,
`"launcherBackend": "auto"` hands the launcher and clipboard over to it and a
bundled plugin lets you drive the shell from Flow's query box (`cp vol 40`).
Setup and the memory trade-off:
[integrations/flow_plugin/README.md](integrations/flow_plugin/README.md).

Without Flow, the built-in launcher and clipboard surfaces do the job. Flow is
never required — the point of this shell is being light.

---

## Layout

```
shell/
  state.py        the morph table and the state machine
  pill.py         the one window
  config.py       one pydantic model, live-reloaded
  theme.py        palette, fonts, glyphs
  widgets.py      hand-painted sliders, cards, marquees
  app.py          wiring: timers, IPC, hotkeys, tray, power
  modules/        state sources that know nothing about the UI
  surfaces/       pages inside the pill, one per state
  platform/       every ctypes call, wrapped
  ipc/            named pipe server, client, grammar
vendor/win32/     yasb's Win32 plumbing, read-only
integrations/     Flow Launcher plugin and theme
tools/            preview renderer, vendoring script
```

The dependency arrow points one way — `shell` → `vendor`, never back, and only
through `shell/platform/`. That is enforced in `tests/test_vendor.py`.

## Development

```
pip install -e ".[dev]"
pytest                                    # morph table, config, IPC, boundaries
QT_QPA_PLATFORM=offscreen python tools/preview.py out/
ruff check . && ruff format --check .
```

The tests run anywhere. Everything platform-specific degrades to a no-op off
Windows, on purpose: it keeps the parts that carry the design — the size table
above all — testable without a Windows box.

## Licence

MIT, except `vendor/` (MIT, © 2024 amnweb) — see [NOTICE](NOTICE).
Note that PyQt6 is GPLv3; that matters if you ship a bundled binary. Details in
[docs/CREDITS.md](docs/CREDITS.md).
