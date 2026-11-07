# The tests of TFT files

These rules are for the tests in this folder: the tests of compiling, decompiling, and uploading TFT files.

## Writing tests

- **What a test checks.** A test states what it checks. It checks one piece through that piece's own function, given the function's own input, such as a page object, a need, or a line of code. It compares the result with expected bytes from a probe's fixture.
- **No whole projects.** A test builds no project, whole or in memory. The exceptions are `test_whole_files.py` and the other modules that `test_unit_test_guard.py` exempts.
- **Inputs.** Inputs come from `unit_inputs.py`: a page from `page()`, and a `Project` from `project_of()`. That `Project` contains only the facts the function reads, never a whole project.
- **Context.** A piece's context, such as its first entry number and its base (`ObjectPlace`), is given as the probe has it. Never rebuild the probe's project to find it.
- **Expected bytes.** Read them with `piece()`, by the piece's name, such as `page0-1-memory`. Never cut them out of a larger part yourself.
- **Shared results.** The helpers keep what they read for the whole run. A test that changes what a helper returned must copy it first.
- **The guard.** `test_unit_test_guard.py` checks the rule on whole projects, and that every `Project` comes from `project_of()`. When a module is converted to these rules, take it off the guard's list of modules not converted yet.
