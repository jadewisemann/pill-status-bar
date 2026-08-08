"""Named pipe IPC.  Protocol in `protocol.py`, transport in `server.py`/`client.py`."""

from shell.ipc.client import NotRunningError, is_running, send, send_raw
from shell.ipc.protocol import (
    ALIASES,
    COMMANDS,
    TARGETS,
    USAGE,
    Command,
    ProtocolError,
    parse_argv,
    parse_message,
    parse_switch,
    parse_value,
)
from shell.ipc.server import PIPE_NAME, IpcServer, reply_error, reply_ok

__all__ = [
    "ALIASES",
    "COMMANDS",
    "Command",
    "IpcServer",
    "NotRunningError",
    "PIPE_NAME",
    "ProtocolError",
    "TARGETS",
    "USAGE",
    "is_running",
    "parse_argv",
    "parse_message",
    "parse_switch",
    "parse_value",
    "reply_error",
    "reply_ok",
    "send",
    "send_raw",
]
