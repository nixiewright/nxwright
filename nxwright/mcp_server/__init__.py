"""nxwright's MCP server, `nxwright mcp`: the tools through which an agent,
a program driven by a language model such as Claude Code, starts the app of
a source folder and drives it as a person drives the simulator.

The server speaks MCP, the Model Context Protocol, on its standard input and
output, through the library zeromcp (server.py). Its tools drive a
DrivenSimulation (simulations.py): a headless one runs in the server's own
process, its time moving only when a tool lets it (headless.py); one in VS
Code runs in a window of VS Code, which the server reaches through the
nxwright extension's agent channel (vscode.py). The tool `about` gives the
agent a guide to the app's files and to the tools (guide.md), and, by
topic, any of nxwright's docs, which ship with the package (server.py,
docs_folder).
"""
