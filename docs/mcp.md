# Letting an agent drive your app

An AI agent, such as Claude Code, Codex, or GitHub Copilot's agent mode, can run your app and use it the way you would: tap its buttons, send it instructions as if they came on its serial line, let its timers run, and see what its screen shows. nxwright gives agents these tools through MCP, the Model Context Protocol, with the command `nxwright mcp`.

## Adding nxwright to your agent

Your agent starts `nxwright mcp` itself, so `nxwright` must be a command it can run, as in a terminal. Add it once:

- **Claude Code:** run `claude mcp add --transport stdio --scope user nxwright -- nxwright mcp`. Without `--scope user`, it is added to the current project alone.
- **Codex:** run `codex mcp add nxwright -- nxwright mcp`, or add these lines to `~/.codex/config.toml`:

  ```toml
  [mcp_servers.nxwright]
  command = "nxwright"
  args = ["mcp"]
  ```

- **GitHub Copilot in VS Code:** add the server to your project's `.vscode/mcp.json`:

  ```json
  {
    "servers": {
      "nxwright": { "type": "stdio", "command": "nxwright", "args": ["mcp"] }
    }
  }
  ```

## What the agent sees

When the agent calls `screen`, it gets the screen's text layout: the page, then one line for each component that shows, with its box and what it shows. For a page with a text, a number, and a button:

```
page page0 (800 x 480), background colour #ffffff
t0  text    20,20   300x40  "Home"
n0  number  20,80   120x40  "2"
b0  button  20,400  160x60  "Next"
```

- Points and boxes are in the page's pixels, from its top left corner. `20,400  160x60` is a box 160 pixels wide and 60 high, 20 pixels from the left edge and 400 from the top.
- The components are listed in the order they are drawn, so a later line lies on top of an earlier one.
- After the components, the layout lists what the app's code painted on the page, such as with `xstr`. Then it gives the names of the components that do not show.
- A picture is given by its ID and by its name in `app.toml`, such as `picture 9 "state/heating"`.
- The agent also gets a picture of the screen, as a PNG file, unless it sets `picture` to false. The files are kept in your computer's temporary folder until `nxwright mcp` ends.

## The tools

| Tool | What it does |
| --- | --- |
| `about` | Gives the agent a guide to read first: your app's files, checking a change, and these tools ([its text](../nxwright/mcp_server/guide.md)). Given a topic, such as `testing`, it gives that doc in full. Each doc in this folder is a topic, apart from the style guide. |
| `start_simulation` | Starts the app of a source folder, from `program.nx`, or on a page without running `program.nx`. With `in_vscode`, it starts it in VS Code ([Simulations in VS Code](#simulations-in-vs-code)). |
| `list_simulations` | Lists the simulations running, those in VS Code included. |
| `screen` | Gives the screen's text layout, and a picture of it. |
| `components` | Lists the components of the page shown, with their boxes. |
| `tap` | Presses the screen and releases it, on a component by its name, or at a point. |
| `press`, `move`, `release` | Hold a press, drag it, and let go. |
| `wait` | Lets time pass, so that the app's timers run, up to a minute at a time. |
| `send` | Sends an instruction, as if it came on the serial line, and gives the log's new lines, such as what the screen sent back. |
| `log` | Lists what the screen received and sent on its serial line. |
| `values` | Reads values, such as `t0.txt` or `sys0`, or every attribute of a component, such as `t0`. |
| `set_input` | Sets a GPIO input's level. |
| `set_inputs` | Sets several GPIO inputs' levels at the same moment. The bound pins' events run once every level has changed, in pin order: nxwright's choice, not checked on a screen. |
| `start_again` | Starts the app again, as a screen switched off and on. |
| `stop_simulation` | Ends a simulation. |

## How the app runs

Unless the agent starts it in VS Code, the app runs inside `nxwright mcp`, without VS Code.

- Its time moves only when the agent lets it. A `wait` of 500 ms runs, at once, everything the app's timers would do in 500 ms.
- It has no serial port. Its SD cards start empty, and their files stay in memory.
- For Chinese input, it uses the installed Nextion Editor's pinyin table, if one is found.

The app runs as it does in the simulator ([Simulating your app](simulator.md)).

## Simulations in VS Code

An agent can also drive a simulation in VS Code, where you watch it in the simulator's panel and can press the screen too. VS Code lets an agent in only once you turn on the setting `nxwright.agents.allowControl` in your user settings. A workspace's settings can't turn it on.

- The agent starts a simulation there with `start_simulation`'s `in_vscode`. The window whose workspace contains the source folder runs it. If several do, the one whose workspace folder lies deepest runs it.
- `list_simulations` lists the simulation each window runs, the one you started included, so that the agent can drive it.
- A window runs one simulation at a time. While one runs, the agent can drive it. To start another there, the agent stops it first.
- The app runs on its own, as you see it run. A `wait` lasts as long on the clock.
- If the window doesn't answer within a minute, as when VS Code hangs, the tool gives up with an error, and the agent can go on with its other tools.
- While an agent drives the simulation, the Simulator section shows it.

### When the serial port reaches a device

A simulation in VS Code can be connected to a real serial port. What the app sends then reaches the device on that port, so:

- A simulation the agent starts has no serial port, whatever the Simulator settings say. To give it the settings' port, turn off `nxwright.agents.startWithoutSerialPort`. VS Code then asks you before the app starts, unless `nxwright.agents.askBeforeSerialActions` is off.
- Before an agent's first action on a simulation whose port is connected, VS Code asks you whether the agent may drive it. Your answer stands until the simulation ends. While you haven't answered, the agent is told that VS Code waits for you.
- If you connect a port from the Simulator section while an agent drives the simulation, VS Code takes that as your yes. The agent may then act on the simulation with that port, without being asked.
- The agent can always read what the screen shows, values, and the log.
- To let an agent act without being asked, turn off `nxwright.agents.askBeforeSerialActions`.
