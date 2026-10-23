"""The language server's answer for making the switch to nxlang from VS Code
(editors/vscode/src/nxlangPanel.ts): the files the switch writes, which the
panel applies in one edit, and the lines of code it changes, which the panel
lists before the user makes it (source_folder.nxlang_switch_files)."""
import difflib
from pathlib import Path

from nxwright.source.source_folder import nxlang_switch_files


def nxlang_switch(source_folder: Path) -> dict:
    """Returns {"files", "changes"}: each file the switch writes, {"path",
    "text"}, by its path in the folder; and each line of code it changes,
    {"file", "line", "before", "after"}, the line counted from 1, in the
    order of the files and their lines. app.toml, which changes its language
    alone, has no lines listed. Raises NxwrightError as the switch does."""
    source_folder = Path(source_folder)
    files = nxlang_switch_files(source_folder)
    changes = []
    for path, text in files.items():
        if not path.endswith(".nx"):
            continue
        before = (source_folder / path).read_text(encoding="utf-8-sig").split("\n")
        after = text.split("\n")
        matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
        for kind, start, end, new_start, new_end in matcher.get_opcodes():
            if kind == "equal":
                continue
            # The switch rewrites lines in place: each changed line, paired
            # with its new text.
            for offset in range(max(end - start, new_end - new_start)):
                changes.append({
                    "file": path, "line": new_start + offset + 1,
                    "before": before[start + offset] if start + offset < end else "",
                    "after": after[new_start + offset] if new_start + offset < new_end else ""})
    return {"files": [{"path": path, "text": text} for path, text in files.items()],
            "changes": changes}
