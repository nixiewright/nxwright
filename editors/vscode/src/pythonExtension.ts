// The Python interpreter chosen in VS Code, through the Python extension's
// API, when that extension is installed. It is the likeliest place for
// nxwright, as in a virtual environment. The extension is optional, so any
// failure of its API means no interpreter is known.

import * as vscode from "vscode";

const PYTHON_EXTENSION = "ms-python.python";

// The part of the Python extension's environments API read here, as the
// package @vscode/python-extension declares it.
interface EnvironmentPath {
  readonly id: string;
  readonly path: string;
}

interface PythonEnvironments {
  getActiveEnvironmentPath(resource?: vscode.Uri): EnvironmentPath;
  resolveEnvironment(
    environment: EnvironmentPath,
  ): Promise<{ readonly executable: { readonly uri: vscode.Uri | undefined } } | undefined>;
  readonly onDidChangeActiveEnvironmentPath: vscode.Event<unknown>;
}

// The interpreter chosen in VS Code for the workspace's first folder.
// `changed` is called when the user chooses another, once the interpreter
// has been asked for.
export class ChosenPython implements vscode.Disposable {
  private environments: Promise<PythonEnvironments | undefined> | undefined;
  private listening: vscode.Disposable | undefined;

  constructor(private readonly changed: () => void) {}

  // Returns the path of the chosen interpreter, or undefined when the Python
  // extension is not installed or knows of none.
  async path(): Promise<string | undefined> {
    const loading = (this.environments ??= this.loadEnvironments());
    const environments = await loading;
    if (environments === undefined && this.environments === loading) {
      // The Python extension may be installed later: asked again next time.
      this.environments = undefined;
    }
    try {
      const chosen = environments?.getActiveEnvironmentPath(
        vscode.workspace.workspaceFolders?.[0]?.uri);
      const resolved = chosen && (await environments?.resolveEnvironment(chosen));
      return resolved?.executable.uri?.fsPath;
    } catch {
      return undefined;
    }
  }

  dispose(): void {
    this.listening?.dispose();
  }

  // Activates the Python extension, which asking for its API needs, and
  // listens for another interpreter being chosen.
  private async loadEnvironments(): Promise<PythonEnvironments | undefined> {
    const extension = vscode.extensions.getExtension<{ environments?: PythonEnvironments }>(
      PYTHON_EXTENSION);
    try {
      const environments = (extension?.isActive ? extension.exports : await extension?.activate())
        ?.environments;
      this.listening = environments?.onDidChangeActiveEnvironmentPath(() => this.changed());
      return environments;
    } catch {
      return undefined;
    }
  }
}
