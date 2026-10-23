"""The numbers a page file's `type` attribute stores for each kind of object,
and their readable names, which nxwright's files and messages use."""

# Readable names of the object types, by the number the `type` attribute stores.
# They follow the Editor's default component names: b0 is a button, bt0 a
# dual-state button, select0 a select, and so on.
TYPE_NAMES = {
    0: "waveform", 1: "slider", 2: "gmov", 3: "video", 4: "audio", 5: "touch-capture",
    51: "timer", 52: "variable", 53: "dual-state-button", 54: "number", 55: "scrolling-text",
    56: "checkbox", 57: "radio", 58: "qr-code", 59: "xfloat", 60: "external-picture",
    61: "combo-box", 62: "sliding-text", 63: "file-stream", 65: "file-browser",
    66: "data-record", 67: "switch", 68: "select", 98: "button", 106: "progress-bar",
    109: "hotspot", 112: "picture", 113: "crop", 116: "text", 121: "page", 122: "gauge",
}
TYPES_BY_NAME = {name: number for number, name in TYPE_NAMES.items()}
