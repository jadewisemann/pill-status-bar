# Risks and how they are handled

Each entry says what is actually implemented, not what could be done.

---

## R1 — Windows has no supported way to suppress its own volume OSD

**Effect:** two overlays for one key press.

**Handling:** ours ships **off**. `"osdEnabled": false` is the default in
`shell/config.py`, and `shell/app.py` checks it before flashing the OSD state.
Users who have removed the system overlay (Windhawk's "Disable Volume OSD"
module, for instance) can turn it on. The OSD surface is fully implemented
either way, so enabling it is a one-key change rather than a build flag.

---

## R2 — `UserNotificationListener` needs an explicit permission grant

**Effect:** no notifications at all until the user allows it in
Settings → Privacy & security → Notifications.

**Handling:** `NotificationsModule` requests access on start and, when refused,
stays alive with `access="denied"` and emits `failed`. `ChillPillApp`
turns that into a tray balloon naming the exact settings page, and
`NotificationsModule.open_permission_settings()` deep-links to
`ms-settings:privacy-notifications`. The shell keeps working without it — the
stack is simply empty, and `chillpillc notify` still pushes entries into it.

---

## R3 — An unpackaged Python process has no AUMID

**Effect:** WinRT notification APIs may refuse to associate with the process.

**Handling:** `set_app_user_model_id()` runs in `run()` before any window
exists. That is the cheap half. The expensive half — registering a Start Menu
shortcut carrying the same AUMID — is **not** implemented; if the listener
still refuses on a given machine, that is the next thing to try. Worth a spike
before relying on notifications in anger.

---

## R4 — AppBar + topmost + fullscreen apps interact badly

**Effect:** the pill floats over games and video.

**Handling:** `foreground_is_fullscreen()` compares the focused window's rect
against its monitor and excludes the desktop and shell classes; `ChillPillApp`
polls it every 1.5 s and hides the pill. Notifications that arrive while hidden
slide in as a separate `FullscreenToast` window instead of being lost.

`ABN_FULLSCREENAPP` — the AppBar's own notification — is **not** wired up; the
geometry check covers borderless-fullscreen games, which is the case the
notification misses. If exclusive-fullscreen apps turn out to slip through,
handling the AppBar callback message is the addition to make.

---

## R5 — Clipboard image cache growth

**Effect:** a day of screenshots quietly eating disk.

**Handling:** `ClipboardModule` caps images at 128 MB under
`%LOCALAPPDATA%\chillpill-win\cliphist\` and evicts oldest-first, and caps the
history at 100 entries. Delegating to Flow avoids the problem entirely; that is
what `"launcherBackend": "auto"` picks when Flow is installed.

---

## R6 — Virtual desktops are not Hyprland workspaces

**Effect:** no dynamic creation, no switch animation, different feel.

**Handling:** the indicator shows real desktops only, capped at
`maxWorkspaces`, and `"workspaceBackend": "none"` hides it. No attempt is made
to simulate workspaces that do not exist.

---

## R7 — Windows increasingly resists focus stealing

**Effect:** the built-in launcher opens without the keyboard.

**Handling:** the pill is `WS_EX_NOACTIVATE` normally; opening the launcher or
clipboard clears that bit and calls vendored `force_foreground_focus`, which
carries the `AttachThreadInput` sequence that still works. Closing restores it.
Delegating to Flow sidesteps the problem, which is a second reason
`"auto"` prefers Flow when it is there.

---

## R8 — The name

**Effect:** trademark and courtesy.

**Handling:** attribution is in `NOTICE` and `docs/CREDITS.md`, no ChillPill
code or assets are used, and alternative names are held in reserve. The
original author has not yet been contacted — that is an open action, not a
resolved one.

---

## Unverified on real hardware

This implementation was written and reviewed on Linux against the Win32/WinRT
documentation and the vendored bindings. The pure layers — morph table, state
machine, config, IPC grammar — are covered by tests, and every surface is
rendered offscreen by `tools/preview.py` at exactly the spec's dimensions.

Everything that touches Windows itself is unexercised until it runs there.
In rough order of how likely each is to need adjustment:

1. AppBar reservation and the top/bottom edge choice
2. DDC/CI brightness on external monitors (per-monitor quirks are the norm)
3. `UserNotificationListener` access and toast text extraction
4. Focus handover to the built-in launcher
5. Acrylic vs. Mica behaviour behind an animated custom-painted radius
