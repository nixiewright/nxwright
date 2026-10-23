// What the Project section of nxwright's side bar shows of a project
// (media/project.mjs draws it): its name, the path as the name's tooltip, a
// note on its source format if needed, then its lines of settings. Kept
// apart from the page's drawing, which test/ cannot run.
//
// Each line is a list of parts, drawn in order:
//  - { text, title? }: words, with a tooltip when `title` is given;
//  - { link, text, title }: words that run the command `link` when
//    clicked, with `title` as their tooltip;
//  - { edit, title }: a pencil button running the command `edit`, with
//    `title` as its tooltip and its name for screen readers.

// How the syntax line names each language of a project's code.
const LANGUAGES = { nxlang: "nxlang", nextion: "strict Nextion" };

// Returns { name, path, note, lines } for `project`, as ProjectView sends it
// (src/projectView.ts): its folder's name and path, what the server says of
// it (`info`, or null before it answers), and the project file, if chosen.
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
  // A chosen project file by its file name, its full path as the tooltip.
  const file = project.projectFile;
  lines.push([
    file ? { text: `Project file: ${file.split(/[\\/]/).pop()}`, title: file }
         : { text: "Project file: none chosen yet" },
    { edit: "nxwright.chooseProjectFile", title: "Choose the project file" },
  ]);
  return { name: project.name, path: project.path, note, lines };
}
