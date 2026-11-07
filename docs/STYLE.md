# Writing style

This file is mostly for agents, whose prose tends to be hard to parse without it. Human contributors should follow the same general guidelines.

nxwright has three kinds of readers: people using it, people looking something up in a reference, and programmers reading its code. Write for the one in front of you.

## People using nxwright

This section covers READMEs, the guides in `docs/`, messages, and the text on the VS Code extension's pages and side bars.

- Write plain, everyday English: common words, in sentences you could say aloud. Drop the phrasing of specs, such as "each ... takes ...", and do not tack on clauses such as "as the Nextion Editor's Device window does".
- Give each sentence one main point, with the facts that qualify it. A run of short sentences sounds robotic, and a long chain of clauses joined by commas and colons is hard to follow.
- Start with what the reader wants to do or know. Then how. Details last.
- Show an example before you explain it. Use real code that runs.
- Talk to the reader: "you".
- Use the future tense for what has not happened yet. A question before an action says what *will* happen: "Every page will be resized", not "Every page is resized".
- Say only what the reader needs to decide or act: what will change, what may be lost, and what to do next. Leave out how nxwright works inside, unless the reader needs it to use nxwright.
- Call things what the user calls them: "the Nextion Editor", "strict Nextion syntax", a command by its title.
- Use the plain word for what you mean. Two words tend to get stretched beyond their normal meaning:
  - "name" is only for a name. Do not use it to mean say, list, show, give, or describe: "the terminal lists the files", not "the terminal names the files"; "the message says which event", not "the message names the event".
  - "hold" is only for keeping something back or in place, as `com_stop` holds the instructions arriving on the serial line until `com_star`. Do not use it to mean contain, have, be, or be set to: "a select's `path` contains its lines", not "holds its lines"; "a button's `val` is 1 while it is pressed", not "a button holds `val` 1"; "another program has the file open", not "another program holds the file".
- Use bullet points for lists of small things, and tables to compare.
- Write each sentence so it can be understood alone: who does what, to what, and when.
  - Say who does the action: "the test creates a data file", not "a data file is made".
  - Spell out conditions with "if" or "when": "if the file doesn't exist and `mode` is 1", not "with `mode` 1, a missing file…".
  - Use the noun itself rather than pointing back with "there", "so", "such", or "as above".
  - Do not end a sentence with a tag, such as ", and the log says so" or "does so". Say what is shown or done, or drop the tag if it adds nothing.
- Things do not ask, want, say, or tell. That goes for attributes, programs, commands, and documents alike:
  - An attribute's value decides, specifies, or sets: "whatever the value of `sendxy`", not "whatever `sendxy` says"; "the screen sends it when `bkcmd` is 2 or 3", not "as `bkcmd` asks".
  - A command prints, prompts for, or warns: "the command prints its size", not "the command tells you how large"; "the command prompts for the device settings", not "the command asks for them".
  - A document documents, or you send the reader to it: "as the vendor's instruction set documents", not "as the instruction set says"; "for the options, see commands.md", not "commands.md says what it asks for".
  - A program accepts code: "the form a program accepts", not "the form it wants".
- Write negatives with "not": "events do not run", "the release does not send a code", not "a touch runs no event" or "sends no code".
  - "Has no" is fine, as in "the page has no background".
  - "Nothing" is fine in a sentence of its own, such as "A tap does nothing". Tacked onto another clause, it squeezes two sentences into one: "A drag scrolls the entries, and does not select any", not "A drag scrolls the entries, and selects nothing".
- Avoid repeating the same words close together, above all at the start of bullet points next to each other. Turning a sentence around often helps, so that it starts with what is new: "The command exits with 1 when a test fails. Testing a folder without tests returns an error.", not "The command exits with 1 when a test fails. The command refuses a folder without tests."
- No em-dashes.

## Reference sections

Lists of commands, options, attributes, or file formats may be dry, but must stay easy to scan: one item per line or subsection, its details and edge cases as short bullets under it, never one long paragraph.

## Comments and docstrings

Write comments and docstrings for a Python programmer who is new to nxwright and to Nextion project files.

- A docstring describes the thing it documents: "Returns the checksum of `directory`.", not "Return ...". It says what the thing does, what it refuses, and what a caller must know, in as many words as that takes but no more. Every module, class, and public function has a docstring. A private function has one when its name is not enough.
- Inline comments say why, not what.
- Define nxwright's terms before using them, and use the names in the glossary below. A module's docstring defines the terms the module relies on.
- Give each sentence one main point, and use real examples rather than shorthand.
- Line length follows the surrounding file, about 100 columns.

## Facts, not how they were found unless it matters

A doc or a comment states what its reader needs to know about how the Nextion Editor behaves. Leave out how that was found and what was tried, unless the reader needs it to understand the behavior.

## Glossary

- **the Nextion Editor:** the vendor's Windows program for designing a screen. It opens, compiles, and simulates project files. Write "the Nextion Editor", never "the Editor" alone: in VS Code, where nxwright's messages show, "the editor" is VS Code's own. Older comments and docstrings still use "the Editor" to mean the Nextion Editor.
- **project file:** a Nextion Editor project, stored as an `.HMI` file made up of named blocks.
- **block:** one named piece of a project file, such as a page (`3.pa`) or a picture (`5.i`).
- **directory:** the list of blocks at the start of a project file, with each block's name, place, size, and flags.
- **live, stale:** a live block is part of the project; a stale one is an old copy the Nextion Editor left when it saved a newer one.
- **manifest:** the block `main.HMI`, which lists the project's pages, pictures, and fonts in order.
- **ID:** the position of a page, picture, or font in the manifest. Code and attributes use the ID to refer to it.
- **page:** one screen of the project, stored as a page block.
- **object:** the page itself (object 0) or one of its components.
- **component:** a thing placed on a page: a text, a button, a timer, a variable, and so on.
- **attribute:** a named value of an object, such as `txt` or `x`.
- **event:** code that runs when something happens to an object, such as `up` when a button is released.
- **strict Nextion syntax:** the language the Nextion Editor reads and the screen runs. Do not call it "Editor code", or "compiled Nextion code", which sounds like the TFT file the Nextion Editor compiles. Older comments and docstrings still use "Editor code" or "the Editor's own language" for it.
- **screen copy:** a picture as the screen draws it, generated from the picture's file.
- **dump:** a project file written out as exact text, for reading and editing.
- **source folder:** a project as files for people and version control: TOML for pages, `.nx` for code, and the project's pictures and fonts.
- **build:** writing a project file from a source folder.
- **extract:** bringing a project file into a source folder.
- **refuse:** to stop with an error. The build refuses a source folder that it cannot turn into a project file. A test or the simulator refuses code that nxwright cannot run, and the run stops.
- **ignore (a line):** what the running screen does with some lines, such as one that sets a `val` to a text. The line has no effect but is reported, and the event carries on. Despite its name, the key `"refusals"` is where a test records an ignored line. The simulator logs the line and sends its error code on the serial line. In prose, do not call an ignored line "refused".
- **nxlang:** the nxwright language, compiled into strict Nextion syntax by the build.
- **generated variable:** a component or `int` the compiler adds to a page to run nxlang: a temporary, a longer-lived text, a control variable, or a function's hotspot.
- **temporary:** a generated variable that stores part of an expression for the length of one statement.
- **hotspot (of a function):** a hidden hotspot component, 2 pixels by 2, whose Touch Press event contains the bodies of the functions at one call depth. A call runs the hotspot with `click`.
