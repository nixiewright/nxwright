"""The framing of the debug adapter's messages: the Debug Adapter Protocol's,
framed as the Language Server Protocol's are. No library frames the side of
a debugger of one's own; the language server's framing is pygls's.

Each message is a JSON object encoded as UTF-8, after a header that gives
its length in bytes:

    Content-Length: 52\\r\\n
    \\r\\n
    {"seq":1,"type":"request","command":"initialize",...}

Other header lines, such as Content-Type, may come before the blank line and
are ignored. The streams are binary, so Windows does not turn "\\n" into
"\\r\\n" and change the length.
"""
import json

from nxwright import NxwrightError


def read_message(stream):
    """Returns the next message of the binary `stream` as a dict, or None when
    the stream ends before a message starts.

    Raises NxwrightError for a header without a length, or a message that is
    cut short or is not a JSON object."""
    length = None
    while True:
        line = stream.readline()
        if not line:
            if length is None:
                return None
            raise NxwrightError("the stream ended inside a message header")
        line = line.rstrip(b"\r\n")
        if not line:
            break
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            if not value.strip().isdigit():
                raise NxwrightError("a message header has a Content-Length that is no number")
            length = int(value.strip())
    if length is None:
        raise NxwrightError("a message header has no Content-Length")
    body = stream.read(length)
    if len(body) != length:
        raise NxwrightError("the stream ended inside a message")
    try:
        message = json.loads(body.decode("utf-8"))
    except ValueError as error:     # also bad UTF-8, which UnicodeDecodeError reports
        raise NxwrightError("a message is not JSON: %s" % error) from None
    if not isinstance(message, dict):
        raise NxwrightError("a message is not a JSON object")
    return message


def write_message(stream, message: dict):
    """Writes `message` to the binary `stream`, with its header, and flushes it."""
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stream.write(b"Content-Length: %d\r\n\r\n" % len(body))
    stream.write(body)
    stream.flush()
