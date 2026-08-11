"""Entry point for the frozen build.

A packaged build has no `pip install`, so the three console scripts declared in
`pyproject.toml` do not exist on the user's PATH.  This dispatcher gives them
back as subcommands of the one executable:

    ChillPill.exe                     start the shell   (chillpill)
    ChillPill-console.exe doctor      check the machine (chillpill-doctor)
    ChillPill-console.exe ctl vol 40  drive the shell   (chillpillc)

`doctor` and `ctl` print, so they are only useful from the console build --
the windowed one has nowhere to print to.  Both executables come out of the
same bundle, so either name accepts either subcommand.
"""

from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    verb = argv[0] if argv else ""

    if verb == "doctor":
        from shell.doctor import main as doctor_main

        return doctor_main()

    if verb == "ctl":
        from shell.cli import main as cli_main

        return cli_main(argv[1:])

    from shell.app import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
