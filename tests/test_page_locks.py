"""Locking a page from VS Code: the edits of the language server's
nxwright/lockPage request, what the other requests say of a locked page, and
the edits they refuse on one."""
import tomllib

from nxwright import NxwrightError
from nxwright.language_server.file_texts import uri_of
from nxwright.project.device_settings import password_hash
from nxwright.source.page_edits import page_lock_edits
from nxwright.source.page_source import page_header_of_text
from tests.language_server_connection import document_item, initialized
from tests.test_page_components import ComponentsTestCase, applied

PAGE0 = "pages/page0.page.toml"
HEADING = 'name = "page0"\ntype = "page"\n'


class LockEditsTest(ComponentsTestCase):

    def lock(self, locked: bool, password: str = None):
        edits = page_lock_edits(self.index(), self.read(), "page0", locked, password)
        self.write(PAGE0, applied(self.text(PAGE0), edits))
        return edits

    def page_table(self) -> dict:
        return tomllib.loads(self.text(PAGE0))["page"]

    def test_lock_writes_the_key_where_extract_writes_it(self):
        self.lock(True)
        self.assertIn(HEADING + "locked = true\nx = 0\n", self.text(PAGE0))
        self.lock(False)
        self.assertIn(HEADING + "x = 0\n", self.text(PAGE0))

    def test_after_a_system_page_mark(self):
        self.write(PAGE0, self.text(PAGE0).replace(HEADING, HEADING + 'system_page = "keyboard"\n'))
        self.lock(True, "abc")
        self.assertIn(HEADING + 'system_page = "keyboard"\nlocked = true\nlock_password_hash = "%s"\n'
                      % password_hash("abc").hex(), self.text(PAGE0))

    def test_a_locked_false_line_is_replaced(self):
        self.write(PAGE0, self.text(PAGE0).replace(HEADING, HEADING + "locked = false\n"))
        self.lock(True)
        self.assertIn(HEADING + "locked = true\nx = 0\n", self.text(PAGE0))

    def test_a_password(self):
        self.lock(True, "abc")
        self.assertEqual(self.page_table()["lock_password_hash"], password_hash("abc").hex())
        # Unlocking does not ask for it, and removes both keys.
        self.lock(False)
        self.assertNotIn("lock", self.text(PAGE0))

    def test_a_leftover_password_is_replaced_or_removed(self):
        leftover = HEADING + 'lock_password_hash = "a1b2c3d4"\n'
        self.write(PAGE0, self.text(PAGE0).replace(HEADING, leftover))
        self.lock(True, "abc")
        self.assertIn(HEADING + 'locked = true\nlock_password_hash = "%s"\nx = 0\n'
                      % password_hash("abc").hex(), self.text(PAGE0))
        self.lock(False)
        self.write(PAGE0, self.text(PAGE0).replace(HEADING, leftover))
        self.lock(True)
        self.assertIn(HEADING + "locked = true\nx = 0\n", self.text(PAGE0))

    def test_passwords_password_hash_refuses(self):
        for password, message in (("", "an empty password"), ("é", "outside ASCII")):
            with self.subTest(password=password):
                with self.assertRaisesRegex(NxwrightError, message):
                    self.lock(True, password)
                self.assertNotIn("lock", self.text(PAGE0))

    def test_nothing_to_do(self):
        self.assertEqual(self.lock(False), [])
        self.lock(True)
        self.assertEqual(self.lock(True, "abc"), [])
        self.assertNotIn("lock_password_hash", self.text(PAGE0))

    def test_an_unknown_lock_value_unlocks(self):
        self.write(PAGE0, self.text(PAGE0).replace(HEADING, HEADING + "locked = 2\n"))
        self.assertTrue(page_header_of_text(self.text(PAGE0), "page0").locked)
        self.lock(False)
        self.assertIn(HEADING + "x = 0\n", self.text(PAGE0))

    def test_the_request(self):
        reply = self.request("nxwright/lockPage", locked=True, password="abc")["result"]
        self.assertEqual(list(reply["changes"]), [uri_of(self.root / PAGE0)])
        self.assertIn("error", self.request("nxwright/lockPage", locked=True, password="é"))
        reply = self.request("nxwright/lockComponents", names=["page0"], locked=True)
        self.assertEqual(reply["error"]["message"],
                         "a page is not locked like a component: use Lock page")


class LockedPageTest(ComponentsTestCase):
    """page0 locked, with a `locked = true` line in its [page] table."""

    def setUp(self):
        super().setUp()
        self.write(PAGE0, self.text(PAGE0).replace(HEADING, HEADING + "locked = true\n"))

    def page_locks(self, folder=None) -> list:
        connection = initialized()
        connection.handle({"jsonrpc": "2.0", "id": 2, "method": "nxwright/pageLocks",
                           "params": {"folder": str(folder or self.root)}})
        return connection.sent[-1]["result"]["locked"]

    def test_the_drawing_and_the_properties_say_so(self):
        self.assertIs(self.request("nxwright/pageDrawing")["result"]["locked"], True)
        properties = self.request("nxwright/componentProperties", name="title")["result"]
        self.assertIs(properties["pageLocked"], True)
        self.write(PAGE0, self.text(PAGE0).replace("locked = true\n", ""))
        self.assertNotIn("locked", self.request("nxwright/pageDrawing")["result"])
        properties = self.request("nxwright/componentProperties", name="title")["result"]
        self.assertIs(properties["pageLocked"], False)

    def test_the_locked_pages(self):
        self.assertEqual(self.page_locks(), ["page0"])
        second = "pages/second.page.toml"
        self.write(second, self.text(second).replace('type = "page"\n',
                                                     'type = "page"\nlocked = 2\n'))
        self.assertEqual(self.page_locks(), ["page0", "second"])
        # A page file that cannot be read is left out.
        self.write(second, "[page\n")
        self.assertEqual(self.page_locks(), ["page0"])

    def test_the_locked_pages_as_the_editor_has_them(self):
        connection = initialized()
        text = self.text(PAGE0).replace("locked = true\n", "")
        connection.handle({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                           "params": {"textDocument": document_item(uri_of(self.root / PAGE0),
                                                                    text)}})
        connection.handle({"jsonrpc": "2.0", "id": 2, "method": "nxwright/pageLocks",
                           "params": {"folder": str(self.root)}})
        self.assertEqual(connection.sent[-1]["result"]["locked"], [])

    def test_edits_are_refused(self):
        copied = self.request("nxwright/copyComponents", names=["title"])["result"]
        requests = {
            "nxwright/addComponent": {"type": "text"},
            "nxwright/deleteComponents": {"names": ["title"]},
            "nxwright/clearEvents": {"names": ["title"]},
            "nxwright/pasteComponents": {"text": copied["text"]},
            "nxwright/pasteParts": {"names": ["title"], "text": copied["text"], "parts": ["size"]},
            "nxwright/placeComponents": {"places": {"title": {"x": 1, "y": 2, "w": 3, "h": 4}}},
            "nxwright/reorderComponents": {"names": ["title"], "direction": "front"},
            "nxwright/lockComponents": {"names": ["title"], "locked": True},
            "nxwright/groupComponents": {"names": ["title"], "grouped": True},
            "nxwright/setAttributes": {"name": "title", "values": {"txt": "y"}},
        }
        for method, params in requests.items():
            with self.subTest(method=method):
                reply = self.request(method, **params)
                self.assertEqual(reply["error"]["message"],
                                 "page0 is locked. Unlock it from the page preview or the "
                                 "Pages section.")
        self.write(PAGE0, self.text(PAGE0).replace("locked = true\n", ""))
        for method, params in requests.items():
            with self.subTest(method=method, unlocked=True):
                self.assertIn("result", self.request(method, **params))

    def test_an_event_opens_but_is_not_added(self):
        # Double-clicking title, or picking one of its events, opens code it
        # has, and does not add the heading of an event without code.
        message = "cannot create event, page0 is locked"
        self.assertEqual(self.request("nxwright/defaultEvent", name="title")["error"]["message"],
                         message)
        self.write("pages/page0.nx", "on title.up:\n  sys0 = 1\n")
        found = self.request("nxwright/defaultEvent", name="title")["result"]
        self.assertEqual((found["line"], found["edit"]), (1, None))
        self.assertEqual(self.request("nxwright/defaultEvent", name="title", event="down")
                         ["error"]["message"], message)
