"""`chillpillc` -- send one command to the running shell and print the reply."""

from __future__ import annotations

import json
import sys

from shell.ipc.client import NotRunningError, send
from shell.ipc.protocol import USAGE, ProtocolError, parse_argv


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0 if argv else 2

    try:
        command = parse_argv(argv)
    except ProtocolError as exc:
        print(f"chillpillc: {exc}", file=sys.stderr)
        return 2

    try:
        reply = send(command)
    except NotRunningError as exc:
        print(f"chillpillc: {exc}", file=sys.stderr)
        return 3
    except RuntimeError as exc:
        print(f"chillpillc: {exc}", file=sys.stderr)
        return 4

    if not reply.get("ok"):
        print(f"chillpillc: {reply.get('error', 'unknown error')}", file=sys.stderr)
        return 1

    result = reply.get("result")
    if isinstance(result, (dict, list)):
        print(json.dumps(result, indent=2))
    elif result is not None:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
