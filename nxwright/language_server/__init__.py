"""The language server: nxwright's answers to a code editor's questions about a
source folder, such as where a name is defined.

It speaks the Language Server Protocol (LSP): JSON messages over standard
input and output, which `nxwright lsp` serves. Any editor that speaks the
protocol can use it; nxwright's own client is the VS Code extension in
editors/vscode.
  - server.py answers them, through pygls, which carries the protocol: its
    messages, the files open in the editor, and the editor's columns.
  - file_texts.py reads a file's text: the editor's while it is open, else
    the file's on disk.
  - source/folder_index.py reads a source folder's names and where each
    one is, and source/definitions.py finds where the name at a place in a
    file is defined; the server answers from them.
"""
