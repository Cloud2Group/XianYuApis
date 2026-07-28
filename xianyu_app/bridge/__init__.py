"""Local bridge for the single-account Xianyu App IM transport.

The bridge deliberately contains no login or credential handling.  The App
side owns the AIM session; this package only moves normalised events and
commands over a permissioned Unix-domain socket.
"""

from .protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    decode_line,
    encode_message,
    make_hello,
    make_message_received,
    make_send_result,
    make_status,
    validate_command,
    validate_event,
)

__all__ = [
    "PROTOCOL_VERSION",
    "ProtocolError",
    "decode_line",
    "encode_message",
    "make_hello",
    "make_message_received",
    "make_send_result",
    "make_status",
    "validate_command",
    "validate_event",
]
