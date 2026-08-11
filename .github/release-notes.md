### Install

Download `{{ZIP}}`, unzip it anywhere, and **run `ChillPill-console.exe doctor` first** —
it names every backend the machine is missing and says what each one costs you.
Then run `ChillPill.exe`.

`ChillPill-console.exe` is the same build with a console attached: run it when you
want to see the log, and use it for the command line —
`ChillPill-console.exe ctl volume 40`, `ChillPill-console.exe ctl toggle controlCenter`.

> **This has not been run on Windows hardware.** Treat the first launch as a debugging
> session, and read [docs/RISKS.md](https://github.com/{{REPO}}/blob/{{TAG}}/docs/RISKS.md)
> first — in particular what an unclean exit does to the desktop work area.

Verify the download against `{{ZIP}}.sha256`:

```powershell
(Get-FileHash {{ZIP}} -Algorithm SHA256).Hash.ToLower()
```

### Licence of the binary

The source in this repository is MIT. **The packaged build is GPLv3**, because it
bundles PyQt6 — a binary containing both is a combined work. `BINARY-LICENSE.md`
inside the zip states the terms and where the corresponding source is;
`requirements-frozen.txt` records the exact dependency versions this build was
frozen against. Running from source is unaffected.

---
