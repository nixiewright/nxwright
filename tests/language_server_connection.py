"""A language server driven as a code editor drives it: each message framed
as the editor frames it, and read by pygls's own loop, as from standard
input; and each message the server writes kept, as the editor would read it.
"""
import io
import json
import threading

from pygls.io_ import run

from nxwright.language_server.server import NxwrightServer

# The params of initialize from an editor that offers nothing beyond the
# protocol's defaults: columns in UTF-16 units, among others.
INITIALIZE_PARAMS = {"processId": None, "capabilities": {}}


class ServerConnection:
    """An NxwrightServer, `server`, given messages by `handle`, with what it
    sends kept in `sent`, a dict per message, in order."""

    def __init__(self):
        self.server = NxwrightServer()
        self.sent = []
        self.server.protocol.set_writer(self, include_headers=False)

    def handle(self, message: dict):
        """Gives the server `message`. A message pygls cannot read is
        reported as `nxwright lsp` reports it (start_io)."""
        body = json.dumps(message).encode("utf-8")
        run(threading.Event(), io.BytesIO(b"Content-Length: %d\r\n\r\n%s" % (len(body), body)),
            self.server.protocol, error_handler=self.server.report_server_error)

    def write(self, data: bytes):
        """Keeps a message the server sends: pygls's writer."""
        self.sent.append(json.loads(data))

    def close(self):
        """pygls closes its writer as the server exits."""


def initialized() -> ServerConnection:
    """Returns a ServerConnection whose server the editor has initialized."""
    connection = ServerConnection()
    connection.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": INITIALIZE_PARAMS})
    return connection


def document_item(uri: str, text: str, version: int = 1) -> dict:
    """Returns the protocol's TextDocumentItem of a file the editor opens,
    with `text`."""
    return {"uri": uri, "languageId": "nx", "version": version, "text": text}
