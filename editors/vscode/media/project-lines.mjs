// What the Project section of nxwright's side bar shows of a project: its
// name, with the path as its tooltip, a note on its source format if needed,
// its lines of settings, and the chain of steps from the source folder to the
// screen, one step for each button. This module works out what to show, and
// media/project.mjs draws it. The drawing is kept apart because the tests
// cannot run it.
//
// Each line, and each step's value, is a list of parts, drawn in order:
//  - { text, title? }: words, with a tooltip when `title` is given;
//  - { link, text, title }: words that run the command `link` when
//    clicked, with `title` as their tooltip;
//  - { edit, title }: a pencil button running the command `edit`, with
//    `title` as its tooltip and its name for screen readers;
//  - { toggle, on, title }: the link button, which runs the command
//    `toggle`, highlighted when `on`, with `title` as its tooltip.
//
// A step is { button, parts }. Its button is { command, glyph, text }, or
// { glyph, text, disabledTitle } when the step cannot run yet. The tooltip
// `disabledTitle` says what to do first.

// How the syntax line names each language of a project's code.
const LANGUAGES = { nxlang: "nxlang", nextion: "strict Nextion" };

// Returns { name, path, note, lines, steps } for `project`, as ProjectView
// sends it (src/projectView.ts): its folder's name and path, what the server
// says of it (`info`, or null before it answers), the project file and the
// TFT file, when chosen, whether Compile also writes the project file
// (`linked`), and the screen, once chosen: { port, rate, model? }, `model`
// as the screen last answered.
export function projectLines(project) {
  const info = project.info;
  let note;
  if (info && info.format < info.currentFormat) {
    note = `The folder is in source format ${info.format}. Upgrade, in this section's ` +
           `header, converts it to format ${info.currentFormat}.`;
  } else if (info && info.format > info.currentFormat) {
    note = `The folder is in source format ${info.format}, which needs a newer nxwright.`;
  }
  const lines = [];
  // A folder whose screen settings the server does not give, as one in an
  // older format, shows none, and so cannot have them changed.
  if (info?.screen) {
    lines.push([
      { text: info.screen },
      { edit: "nxwright.changeScreen", title: "Change the screen model" },
      { text: ` · ${info.size} · ${info.rotation}°` },
      { edit: "nxwright.changeRotation", title: "Change the rotation" },
      { text: ` · ${info.encoding}` },
      { edit: "nxwright.changeEncoding", title: "Change the character encoding" },
    ]);
  }
  if (info?.language === "nextion") {
    // Strict Nextion syntax can be switched to nxlang, which a link says
    // plainly; nxlang cannot be switched back.
    lines.push([{ text: `Syntax: ${LANGUAGES.nextion} (` },
                { link: "nxwright.switchToNxlang", text: "switch to nxlang",
                  title: "Open the Switch to nxlang panel" },
                { text: ")" }]);
  } else if (info?.language) {
    lines.push([{ text: `Syntax: ${LANGUAGES[info.language] ?? info.language}` }]);
  }
  return { name: project.name, path: project.path, note, lines, steps: steps(project) };
}

// The steps of the chain: the project file, which Build writes, the TFT
// file, which Compile writes, and the screen, which Upload writes to. Each
// chosen file shows by its name, its full path as the tooltip, and the
// screen by its port and upload rate.
function steps(project) {
  const projectFile = project.projectFile;
  const projectName = projectFile && fileName(projectFile);
  const projectParts = [
    projectFile ? { text: projectName, title: projectFile } : { text: "no project file" },
    { edit: "nxwright.chooseProjectFile", title: "Choose the project file" },
  ];
  if (projectFile) {
    projectParts.push({
      toggle: "nxwright.toggleProjectFileLink", on: Boolean(project.linked),
      title: project.linked
        ? `Compile also writes ${projectName}. Click to leave it as it is.`
        : `Compile leaves ${projectName} as it is. Click to have Compile write it too.`,
    });
  }
  const tftFile = project.tftFile;
  return [
    // With no project file, there is nothing to build yet, so the button is
    // disabled. It stays in place to show that the step exists.
    { button: projectFile
        ? { command: "nxwright.build", glyph: "build", text: "Build HMI" }
        : { glyph: "build", text: "Build HMI", disabledTitle: "Choose a project file first" },
      parts: projectParts },
    { button: { command: "nxwright.compile", glyph: "compile", text: "Compile TFT" },
      parts: [tftFile ? { text: fileName(tftFile), title: tftFile } : { text: "no TFT file" },
              { edit: "nxwright.chooseTftFile", title: "Choose the TFT file" }] },
    { button: { command: "nxwright.upload", glyph: "upload", text: "Upload TFT" },
      parts: [screenPart(project.screen),
              { edit: "nxwright.chooseScreen",
                title: "Choose the screen's port and upload rate" }] },
  ];
}

function screenPart(screen) {
  if (!screen) {
    return { text: "no screen" };
  }
  const text = `${screen.port} · ${screen.rate}`;
  return screen.model
    ? { text, title: `The screen on ${screen.port} last answered as ${screen.model}` }
    : { text };
}

function fileName(file) {
  return file.split(/[\\/]/).pop();
}
