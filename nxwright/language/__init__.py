"""The code in a source folder, turned into code the Nextion Editor accepts.

  - nxlang: the nxwright language, compiled into Editor code.
  - code_preprocessor: comfortable code, Editor code written more freely,
    turned into the syntax the Editor accepts.
  - code_checks: the checks of code for what the Nextion Editor refuses.
  - code_lines: the parts of one line of code, which the build and the
    code editor's tools read.
  - editor_code: Editor code coming into a source folder that uses nxlang.
  - resource_names: the names that stand for pictures, fonts, animations,
    videos, and sounds, as in "@pic(name)".
"""
