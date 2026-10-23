// What the client's parts say to the user alike.

// Returns the text of `error` to show the user: an Error's message, or else
// the thing thrown, as text.
export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
