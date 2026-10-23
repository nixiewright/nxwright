// The oldest nxwright toolchain this extension works with, and the warning for
// an older one. Kept apart from VS Code, so that its tests run without it.

// Raise it when the extension starts relying on something only a newer
// toolchain has, such as a new request to the language server, to the
// version that carries it (CONTRIBUTING.md, Versions).
export const OLDEST_TOOLCHAIN = "0.1.0";

// Returns whether the version `version`, such as "0.1.0", is older than
// `oldest`, comparing their dotted numbers one by one, a missing one as 0.
// A version that does not read as dotted numbers is not older, so that
// nothing is warned of by mistake.
export function isOlder(version: string, oldest: string): boolean {
  const numbers = (text: string) =>
    /^\d+(\.\d+)*$/.test(text) ? text.split(".").map(Number) : undefined;
  const given = numbers(version);
  const wanted = numbers(oldest);
  if (given === undefined || wanted === undefined) {
    return false;
  }
  for (let index = 0; index < Math.max(given.length, wanted.length); index++) {
    const difference = (given[index] ?? 0) - (wanted[index] ?? 0);
    if (difference !== 0) {
      return difference < 0;
    }
  }
  return false;
}

// Returns the warning for the toolchain whose language server reports
// `version`, or undefined when it is recent enough. A server that reports no
// version runs from a copy of nxwright's source that is not installed, which
// is not checked.
export function toolchainWarning(version: string | undefined,
                                 oldest = OLDEST_TOOLCHAIN): string | undefined {
  if (version === undefined || !isOlder(version, oldest)) {
    return undefined;
  }
  return `nxwright: this extension needs nxwright ${oldest} or later, and the one installed is ` +
    `${version}. To update it, run git pull in your copy of nxwright, then pip install . there.`;
}

// Returns a function to call with the version each start of the language
// server reports. It calls `show` with the warning the first time one is due,
// and never again: the server restarts with the same toolchain, so once a
// session is enough.
export function warnerOnce(show: (warning: string) => void,
                           oldest = OLDEST_TOOLCHAIN): (version: string | undefined) => void {
  let warned = false;
  return (version) => {
    const warning = toolchainWarning(version, oldest);
    if (warning !== undefined && !warned) {
      warned = true;
      show(warning);
    }
  };
}
