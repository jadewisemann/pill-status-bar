"""`python -m shell` starts the shell; `python -m shell.cli` talks to it."""

from shell.app import run

if __name__ == "__main__":
    raise SystemExit(run())
