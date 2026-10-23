// The page of each of the extension's webviews: the page preview's, the
// Attributes section's, and the simulator's panel and section.
import * as vscode from "vscode";

export interface WebviewPageContent {
  // The file of media/ that runs the page, or none for a page with no script.
  script?: string;
  // The markup of its body, and its styles.
  body: string;
  styles: string;
  // Whether it may show pictures: the source folder's, and data: URLs.
  allowImages?: boolean;
  // Whether it may play audio, from the folders its webview's options allow.
  allowMedia?: boolean;
}

// The styles of the zoom bar (media/zoom.mjs), in the preview's toolbar
// and above the simulator's screen.
export const ZOOM_STYLES = `
  .zoom { display: flex; align-items: center; gap: 2px; }
  .zoom[hidden] { display: none; }
  .zoom button {
    min-width: 26px; padding: 2px 6px; border: none; cursor: pointer;
    color: var(--vscode-button-secondaryForeground);
    background: var(--vscode-button-secondaryBackground);
  }
  .zoom button:hover { background: var(--vscode-button-secondaryHoverBackground); }`;

// What the webview loads a picture of a drawing from, as the language server
// gives it (testing/preview.py, picture_file): its file's path; or, for a picture
// file of an SD card in PictureBox's form, its JPEG picture's data URL and,
// when it has transparency, its mask's; or, for a picture whose file asks
// to be turned, which the Editor does not do, a data URL of its pixels as
// stored; and its file's version.
export interface PictureFile {
  path?: string;
  data?: string;
  mask?: string;
  version: string;
}

// Returns, for `webview`, each picture's address by its name, and each
// mask's: a data URL as it is; a file as a webview address, its version
// part of it, since the webview keeps pictures by their address.
export function pictureSources(webview: vscode.Webview, files: Record<string, PictureFile>):
    { pictureUris: Record<string, string>; pictureMasks: Record<string, string> } {
  const pictureUris: Record<string, string> = {};
  const pictureMasks: Record<string, string> = {};
  for (const [name, file] of Object.entries(files)) {
    if (file.data !== undefined) {
      pictureUris[name] = file.data;
    } else if (file.path !== undefined) {
      const uri = webview.asWebviewUri(vscode.Uri.file(file.path));
      pictureUris[name] = uri.with({ query: `v=${file.version}` }).toString();
    }
    if (file.mask !== undefined) {
      pictureMasks[name] = file.mask;
    }
  }
  return { pictureUris, pictureMasks };
}

// Returns a webview's page. Its content security policy lets it load only
// the extension's own scripts and inline styles, and pictures and audio when
// asked.
export function webviewPage(webview: vscode.Webview, extensionUri: vscode.Uri,
                            content: WebviewPageContent): string {
  const script = content.script &&
    webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, "media", content.script));
  const policy = [
    "default-src 'none'",
    ...(content.allowImages ? [`img-src ${webview.cspSource} data:`] : []),
    ...(content.allowMedia ? [`media-src ${webview.cspSource}`] : []),
    ...(script ? [`script-src ${webview.cspSource}`] : []),
    "style-src 'unsafe-inline'",
  ].join("; ");
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${policy}">
<style>
${content.styles}
</style>
</head>
<body>
${content.body}
${script ? `<script type="module" src="${script}"></script>` : ""}
</body>
</html>`;
}
