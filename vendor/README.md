# vendor/

Third-party code, kept separate from `shell/` on purpose.

## Rules

1. **Do not edit anything under `vendor/win32/`.** The only change applied to
   these files is a mechanical rewrite of import paths. If behaviour needs to
   change, write an adapter in `shell/platform/` and call into vendor from
   there.
2. Nothing in `shell/` may be imported from `vendor/`. The dependency arrow
   points one way.
3. Re-importing from upstream is a scripted operation, not a manual merge —
   see below.

## What is here

| Path | Origin | Licence |
| --- | --- | --- |
| `win32/` | [yasb](https://github.com/amnweb/yasb) `src/core/utils/win32/` @ `95089f3` | MIT © 2024 amnweb (`LICENSE.yasb`) |
| `compat/events.py` | written for this project | MIT (project licence) |

`compat/events.py` exists because `win32/hotkeys.py` is vendored verbatim and
dispatches through yasb's application-wide event bus. Rather than patch the
vendored file, the import is rewritten to point at a two-method stand-in.

`win32/utils.py` is a **partial extract**, not a full copy: upstream's version
pulls in WinRT's `PackageManager` and a yasb-internal helper for functionality
this project does not use. Only the monitor and foreground helpers are here.

## Re-importing from upstream

```
git clone --depth 1 https://github.com/amnweb/yasb /tmp/yasb
python tools/vendorize.py --source /tmp/yasb/src/core/utils/win32
python -m pytest tests/test_vendor.py
```

`tools/vendorize.py` copies the file list, inserts the provenance header and
applies the import rewrites. `tests/test_vendor.py` checks that no
yasb-internal import survived the rewrite.

## What was deliberately not vendored

yasb's widget layer (`widgets/yasb/`, ~27k lines), its settings UI, its
per-widget validation schemas and its service layer. Where the same Windows
API was needed, yasb's service code was read as documentation and reimplemented
in `shell/modules/` against this project's own module contract.
