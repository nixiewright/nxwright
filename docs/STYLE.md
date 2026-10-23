# Writing style

# Audience

This file is mostly aimed at agents, whose prose otherwise tends to be difficult to parse. Humans contributors are still expected to adhere to those general guidelines.

nxwright's words reach three kinds of readers: people using nxwright, readers looking something up in a reference, and programmers reading its code. Write for the one in front of you.

## People using nxwright

READMEs, the guides in `docs/`, messages, and the words on VS Code's pages and side bars.

- Write plain, everyday English: short sentences, common words, generally one idea each. Drop the phrasing of specs, such as "as the Nextion Editor's Device window does", "each ... takes ...", or a chain of clauses joined by commas and colons.
- Start with what the reader wants to do or know. Then how. Details last.
- Show an example before you explain it. Use real code that runs.
- Talk to the reader: "you".
- Use the future tense for what has not happened yet. A question before an action says what *will* happen: "Every page will be resized", not "Every page is resized".
- Say only what the reader needs to decide or act: what will change, what may be lost, and what to do next. Leave out how nxwright works inside, unless the reader needs it to use nxwright.
- Call things what the user calls them: "the Nextion Editor", "strict Nextion syntax", a command by its title.
- Use the plain word for what you mean. Two words tend to drift into a private sense:
  - "name" is only for a name. Do not use it to mean say, list, show, give, or describe: "the terminal lists the files", not "the terminal names the files"; "the message says which event", not "the message names the event".
  - "hold" is only for keeping something back or in place, as `com_stop` holds the instructions arriving on the serial line until `com_star`. Do not use it to mean contain, have, be, or be set to: "a select's `path` contains its lines", not "holds its lines"; "a button's `val` is 1 while it is pressed", not "a button holds `val` 1"; "another program has the file open", not "another program holds the file".
- Use bullet points for lists of small things, and tables to compare.
- Write each sentence so it can be understood alone: who does what, to what, and when. Say who does the action: "the test creates a data file", not "a data file is made". Spell out conditions with "if" or "when": "if the file doesn't exist and `mode` is 1", not "with `mode` 1, a missing file…". Do not point back with "there", "so", "such", or "as above" when the noun can be named instead. The same goes for a tag at the end of a sentence, such as ", and the log says so" or "does so": say what is shown or done, or drop the tag if it adds nothing.
- Things do not ask, want, say, or tell. That goes for attributes, programs, commands, and documents alike:
  - An attribute's value decides, specifies, or sets: "whatever the value of `sendxy`", not "whatever `sendxy` says"; "the screen sends it when `bkcmd` is 2 or 3", not "as `bkcmd` asks".
  - A command prints, prompts for, or warns: "the command prints its size", not "the command tells you how large"; "the command prompts for the device settings", not "the command asks for them".
  - A document documents, or the reader sees it: "as the vendor's instruction set documents", not "as the instruction set says"; "for the options, see commands.md", not "commands.md says what it asks for".
  - Code is in the form a program accepts, not the form it wants.
- Write negatives with "not": "events do not run", "the release does not send a code", not "a touch runs no event" or "sends no code". "Has no", as in "the page has no background", is fine. So is "nothing" in a sentence of its own, such as "A tap does nothing". Avoid tacking a "nothing" clause onto another one, which squeezes two sentences into one: "A drag scrolls the entries, and does not select any", not "A drag scrolls the entries, and selects nothing".
- Avoid repeating the same words close together, above all at the start of bullet points next to each other. Turning a sentence around often helps, so that it starts with what is new: "The command exits with 1 when a test fails. Testing a folder without tests returns an error.", not "The command exits with 1 when a test fails. The command refuses a folder without tests."
- No em-dashes.

## Reference sections

Lists of commands, options, attributes, or file formats may be dry, but must stay easy to scan: one item per line or subsection, its details and edge cases as short bullets under it, never one long paragraph.

## Comments and docstrings

Written for a Python programmer who is new to nxwright and to Nextion project files.

- Docstrings describe: "Returns the checksum of `directory`.", not "Return ...". They say what a thing does, what it refuses, and what a caller must know, in as many words as that takes but no more. Every module, class, and public function has one; a private function has one when its name is not enough.
- Inline comments say why, not what.
- Define nxwright's terms before using them, and use the names in the glossary below. A module's docstring defines the terms the module relies on.
- Short sentences, one idea each, and real examples rather than shorthand.
- Line length follows the surrounding file, about 100 columns.

## Facts, not how they were found unless it matters

A doc or a comment states what its reader needs to know about how the Nextion Editor behaves. How that was found out, and what was tried, does not belong in it unless this provides important background the user requires to understand the behavior.

## Glossary

- **the Nextion Editor:** the vendor's Windows program for designing a screen. It opens, compiles, and simulates project files. Write "the Nextion Editor", never "the Editor" alone: in VS Code, where nxwright's messages show, "the editor" is VS Code's own. Older comments and docstrings still say "the Editor", which means the same.
- **project file:** a Nextion Editor project, `.HMI`: a container of named blocks.
- **block:** one named piece of a project file, such as a page (`3.pa`) or a picture (`5.i`).
- **directory:** the list of a project file's blocks, at its start: each block's name, place, size, and flags.
- **live, stale:** a live block is part of the project; a stale one is an old copy the Nextion Editor left when it saved a newer one.
- **manifest:** the block `main.HMI`, which lists the project's pages, pictures, and fonts in order.
- **ID:** a page's, picture's, or font's position in the manifest, which code and attributes use to name it.
- **page:** one screen of the project, stored as a page block.
- **object:** the page itself (object 0) or one of its components.
- **component:** a thing placed on a page: a text, a button, a timer, a variable, and so on.
- **attribute:** a named value of an object, such as `txt` or `x`.
- **event:** code that runs when something happens to an object, such as `up` when a button is released.
- **strict Nextion syntax:** the language the Nextion Editor reads and the screen runs, which nxlang builds to. Not "Editor code", nor "compiled Nextion code", which reads like the Nextion Editor's compile to a TFT file. Older comments and docstrings still say "Editor code" or "the Editor's own language" for it.
- **screen copy:** a picture as the screen draws it, generated from the picture's file.
- **dump:** a project file written out as exact text, for reading and editing.
- **source folder:** a project as files for people and version control: TOML for pages, `.nx` for code, pictures, and fonts.
- **refuse:** to stop with an error. The build refuses a source folder it cannot write. A test or the simulator refuses code that nxwright cannot run, and the run stops.
- **ignore (a line):** what the running screen does with some lines, such as a `val` given a text. The line changes nothing, and is reported. The event goes on. A test records an ignored line under `"refusals"`. The simulator logs it, and answers its error code on the serial line. Do not call this "refused".
- **build:** writing a project file from a source folder. **Extract:** bringing a project file into a source folder.
- **nxlang:** the nxwright language, compiled into strict Nextion syntax by the build.
- **generated variable:** a component or `int` the compiler adds to a page to run nxlang: a temporary, a longer-lived text, a control variable, or a function's hotspot.
- **temporary:** a generated variable holding part of an expression for the length of one statement.
- **hotspot (of a function):** a hidden 2 by 2 hotspot whose Touch Press event holds the bodies of the functions of one call depth; a call runs it with `click`.
