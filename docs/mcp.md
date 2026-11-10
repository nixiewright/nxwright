# Letting an agent drive your app

An AI agent, such as Claude Code, Codex, or GitHub Copilot's agent mode, can run your app and use it the way you would: tap its buttons, send it instructions as if they came on its serial line, let its timers run, and see what its screen shows. nxwright gives agents the tools for this through MCP, the Model Context Protocol, with the command `nxwright mcp`.

## Adding nxwright to your agent

Your agent starts `nxwright mcp` itself, so it must be able to run `nxwright` the way you do in a terminal. To add nxwright to your agent:

- **Claude Code:** run `claude mcp add --transport stdio --scope user nxwright -- nxwright mcp`. Leave out `--scope user` to add nxwright to the current project only.
- **Codex:** run `codex mcp add nxwright -- nxwright mcp`, or add these lines to `~/.codex/config.toml`:

  ```toml
  [mcp_servers.nxwright]
  command = "nxwright"
  args = ["mcp"]
  ```

- **GitHub Copilot in VS Code:** add nxwright to your project's `.vscode/mcp.json`:

  ```json
  {
    "servers": {
      "nxwright": { "type": "stdio", "command": "nxwright", "args": ["mcp"] }
    }
  }
  ```

## What the agent sees

When the agent calls `screen`, it gets a text layout of the page and a picture of the screen. The picture is a PNG file, kept in your computer's temporary folder until `nxwright mcp` ends. For a page with a text, a number, and a button, the text layout is:

```
page page0 (800 x 480), background colour #ffffff
t0  text    20,20   300x40  "Home"
n0  number  20,80   120x40  "2"
b0  button  20,400  160x60  "Next"
```

After the page's line, each line gives a visible component's name, type, box, and content. See the [agent guide](../nxwright/mcp_server/guide.md) for more on the layout.

## The tools

| Tool | What it does |
| --- | --- |
| `about` | Gives the agent a [guide](../nxwright/mcp_server/guide.md) to read first, on your app's files, how to check a change, and these tools. The agent can also ask for any doc in this folder except the style guide, by giving a topic such as `testing`. |
| `start_simulation` | Starts the app of a source folder, either from `program.nx` or on a given page without running `program.nx`. With `in_vscode`, the app runs in VS Code ([Simulations in VS Code](#simulations-in-vs-code)). |
| `list_simulations` | Lists the running simulations, including those in VS Code. |
| `screen` | Gives the screen's text layout, and a picture of it. |
| `components` | Lists the components of the page shown, with their boxes. |
| `tap` | Presses and releases a component, given by its name, or a point on the screen. |
| `press`, `move`, `release` | Hold a press, drag it, and let go. |
| `wait` | Lets time pass, up to a minute at a time, so that the app's timers run. |
| `send` | Sends an instruction, as if it came on the serial line, and gives the log's new lines, such as what the screen sent back. |
| `log` | Lists what the screen received and sent on its serial line. |
| `values` | Reads values, such as `t0.txt` or `sys0`, or every attribute of a component, such as `t0`. |
| `set_input` | Sets a GPIO input's level. |
| `set_inputs` | Sets several GPIO inputs' levels at the same moment. Once every level has changed, the events bound to those pins run in pin order. nxwright chose this order, and it has not been checked on a real screen. |
| `start_again` | Starts the app again, like a screen being switched off and on. |
| `stop_simulation` | Ends a simulation. |

## How the app runs

By default, the app runs inside `nxwright mcp`, without VS Code. It behaves the same way as in the simulator ([Simulating your app](simulator.md)), with these differences:

- The app's time moves only when the agent calls `wait`. A `wait` of 500 ms immediately runs everything the app's timers would do in 500 ms.
- The app has no serial port.
- SD cards start empty, and their files stay in memory.
- For Chinese input, the app uses the installed Nextion Editor's pinyin table, if one is found.

## Simulations in VS Code

An agent can also drive a simulation in VS Code, where you can watch it in the simulator's panel and press the screen too. To allow this, turn on the setting `nxwright.agents.allowControl` in your user settings. A workspace's settings can't turn it on.

A few things to know about simulations in VS Code:

- The app runs on its own in real time, and a `wait` of 500 ms takes 500 ms.
- An agent's simulation runs in the window whose workspace contains the source folder. If several windows do, it runs in the one whose workspace folder is nested deepest.
- `list_simulations` includes any simulation you started yourself, so the agent can drive those too.
- A window runs one simulation at a time. The agent can drive the one running, but must stop it before starting another in that window.
- If the window doesn't answer within a minute, for example because VS Code has hung, the tool gives up with an error, and the agent can still use its other tools.

### When the serial port reaches a device

A simulation in VS Code can be connected to a real serial port, and what the app sends then reaches the device on that port. By default, an agent can't reach that device without your permission:

- A simulation the agent starts has no serial port, whatever the Simulator settings are. To have it use the port from those settings, turn off `nxwright.agents.startWithoutSerialPort`. VS Code then asks you before the app starts, unless `nxwright.agents.askBeforeSerialActions` is off.
- Before an agent's first action on a simulation whose port is connected, VS Code asks you whether the agent may drive it. Your answer stands until the simulation ends.
- If you connect a port from the Simulator section while an agent drives the simulation, VS Code treats that as your permission, and will not ask you.
- Reading what the screen shows, values, and the log never needs your permission.
- An agent never reaches a real screen connected beside the simulation ([A real screen](simulator.md#a-real-screen)), even with your permission.
- To let agents act without asking you, turn off `nxwright.agents.askBeforeSerialActions`.
