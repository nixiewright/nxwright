# Writing an MCU emulator

On real hardware, a microcontroller (MCU) sits at the other end of your screen's serial line. An MCU emulator is a Python program that takes its place while your app runs in the simulator, so you can try the app without the hardware. The thermostat demo has one ([examples/thermostat](https://github.com/nixiewright/nxwright/tree/main/examples/thermostat)).

## Adding an emulator to a project

```
nxwright new-emulator app
```

`new-emulator` writes a first program to `mcu/main.py`, in a folder beside the source folder, and records the program's path in `app.toml` ([commands.md](commands.md#new-emulator)).

## The program

```python
from nxwright import mcu

END = b"\xff\xff\xff"
READY = b"\x88" + END

with mcu.open(listen=7000) as line:
    while True:
        message = line.read_until(END)
        if message == READY:
            line.write(b't0.txt="Hello"' + END)
```

This emulator sets the text of `t0` when your app starts. To know when, it waits for the screen to send "ready" ([Start-up and ready](simulator.md#start-up-and-ready)). The program that `new-emulator` writes has the same loop, with comments where your own code goes, and takes its port number from the command line.

`mcu.open(listen=7000)` waits for the simulator to connect to port 7000 of your computer, then returns the screen's serial line. The line carries bytes exactly as they are, so you add the FF FF FF that ends each instruction, and each message from the screen arrives with its own FF FF FF ([The serial line](simulator.md#the-serial-line)).

The line has the members of pyserial's `Serial` that an emulator needs, so code written for a serial port works on it unchanged:

| Member | What it does |
| --- | --- |
| `read(size=1)` | Returns the next `size` bytes the screen sent. |
| `read_until(expected=b"\n", size=None)` | Returns the bytes up to and including `expected`, and no more than `size` bytes if you give it. |
| `write(data)` | Sends `data` to the screen, and returns how many bytes it sent. |
| `in_waiting` | How many bytes a read would return without waiting. |
| `timeout` | How long a read waits, in seconds. `None`, the default, waits until the bytes have come, and `0` does not wait. |
| `sleep(seconds)` | Waits for `seconds` seconds. pyserial's `Serial` does not have this member. |
| `close()` | Closes the line. A `with` block closes it for you. |

- If `timeout` passes before a read has all its bytes, the read returns the bytes that have come, which may be none.
- When the simulation ends, a read or a write raises `mcu.LineClosed`. Catch it to end your program.
- To wait, use `line.sleep` or a read's `timeout`, and do not use `time.sleep`. A later version of nxwright may run your app on a simulated clock, and `time.sleep` would not follow that clock.
- Some of the screen's messages can contain FF bytes, so `read_until` may stop inside them. For example, the reply to a `get` of a number is 8 bytes long and can contain FF bytes, so read it with `line.read(8)`.

## Running the emulator

The emulator needs nxwright installed in the Python environment that runs it, and nothing else, because `nxwright.mcu` uses only Python's standard library.

### Started with the simulation

In VS Code, a simulation whose MCU port is Emulator starts the project's emulator. A project that has an emulator starts its simulations with that port, unless you chose another port for the project earlier, or set one in the Simulator settings ([The port a simulation starts with](simulator.md#the-port-a-simulation-starts-with)).

- VS Code needs the Python Debugger extension to start the emulator, and runs it with the Python interpreter selected in VS Code.
- When you debug the simulation, the emulator is debugged too, so breakpoints work in its code.
- Your app waits up to 10 seconds for the emulator to connect before the app starts, so that the emulator receives the start-up code and "ready". You can change that time with `wait` in the `[mcu]` table of `app.toml` ([app.toml](source-folder.md#apptoml)), or with a launch configuration's `emulatorWait`.
- "Start the emulator again", in the Simulator section, restarts the emulator while your app keeps running. "Start again" restarts your app alone, and the emulator then receives the start-up code and "ready" again.
- If you stop the emulator, the simulation keeps running.
- To give the emulator its own interpreter, arguments, or environment variables, add a launch configuration of the Python Debugger whose `program` is the emulator's file. VS Code then starts the emulator with that configuration.

### The simulator listens

Without the Python Debugger extension, VS Code does not start the emulator, and your app starts without waiting for one. The simulator still listens for an emulator that you start yourself.

1. Start the simulation with the Emulator port. The Simulator section of nxwright's side bar shows the address the simulator listens at, such as `127.0.0.1:53124`.
2. Start the emulator with that address in the environment variable `NXWRIGHT_MCU`. `mcu.open` then connects to the simulator, whatever `listen` is.

   ```
   # PowerShell
   $env:NXWRIGHT_MCU = "127.0.0.1:53124"; python mcu/main.py

   # Linux and macOS
   NXWRIGHT_MCU=127.0.0.1:53124 python mcu/main.py
   ```

- The simulator keeps listening at the same address until the simulation ends, or until you choose another MCU port, so you can stop the emulator and start it again while your app keeps running. The next simulation listens at a new address.
- One emulator is connected at a time. What your app sends while none is connected is lost. If your app started before the emulator connected, the emulator has missed the start-up code and "ready". Use "Start again" in the Simulator section to make your app send them again.

### The emulator listens

The emulator can also listen at an address of its own, which stays the same from one simulation to the next.

1. Start the emulator with a port number, as in `python mcu/main.py 7000`. It then waits for the simulator to connect.
2. Start the simulation.
3. In the Simulator section, choose TCP in the MCU port list, enter `127.0.0.1:7000`, and connect ([A program over TCP](simulator.md#a-program-over-tcp)).

The simulator remembers the port, so the project's next simulations connect when they start. Start the emulator before each one, because it serves one simulation and ends when that simulation ends.
