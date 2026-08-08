# ChillPill plugin for Flow Launcher

Lets you drive the shell from Flow's query box: `cp vol 40`, `cp timer 10`,
`cp clip`, and so on.

## Why this exists

Flow is a single-instance app whose second-instance handler only calls
`API.ShowMainWindow()` — it takes no arguments and registers no URL scheme, so
nothing outside Flow can open it *with a query already typed*. The useful
direction is the other one: a plugin inside Flow can call out to anything. So
ChillPill does not try to drive Flow; it lets Flow drive ChillPill.

## Division of labour

| | Handled by |
| --- | --- |
| App launching, file search, calculator, web search | Flow |
| Clipboard history, wallpaper picking | Flow (this plugin) or ChillPill's own surfaces |
| Volume, brightness, DND, timers, surface toggles | this plugin → the pipe |
| Pill bar, control center, dashboard, OSD, notifications | ChillPill |

Set `"launcherBackend"` in the shell's config to choose:

* `"auto"` (default) — delegate to Flow when it is installed, otherwise use the
  built-in launcher and clipboard surfaces
* `"flow"` — always delegate
* `"builtin"` — never delegate

## The trade-off, stated plainly

Running both means two processes and two runtimes (.NET/WPF and Python/Qt),
which costs roughly 150–250 MB of RAM. ChillPill's whole premise is being light
enough for a machine without a GPU, so Flow is an **optional** integration, not
a dependency. The built-in launcher and clipboard surfaces are fully functional
on their own.

## Install

```
xcopy /E /I integrations\flow_plugin "%APPDATA%\FlowLauncher\Plugins\ChillPill"
copy integrations\flow_plugin\Themes\ChillPill.xaml "%APPDATA%\FlowLauncher\Themes\"
```

Restart Flow, then pick the **ChillPill** theme under Settings → Appearance so
the launcher and the pill share one palette.

## Commands

| Query | Does |
| --- | --- |
| `cp` | list everything |
| `cp vol 40` / `cp vol +5` | set or step the volume |
| `cp bri 60` | set brightness |
| `cp timer 10` / `cp timer cancel` | countdown |
| `cp dnd` | do-not-disturb on/off |
| `cp wall` | open the wallpaper switcher |
| `cp clip` | open clipboard history |

## Protocol notes

Flow passes the JSON-RPC request as `argv[1]` and reads the response from
stdout; `main.py` also accepts the request on stdin, because some builds pipe
it instead. Actions run `send()`, which writes one JSON line to
`\\.\pipe\chillpill_ipc` — the same pipe `chillpillc` uses, so anything this
plugin can do is scriptable without it.

The plugin imports nothing from the shell's Python packages. It can be copied
out of this repo and it will keep working.
