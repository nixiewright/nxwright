// Which controls the Simulator section (simulator-controls.mjs) shows and
// enables, depending on whether the MCU port is joined to a real screen in
// place of the simulator (nxwright/debug_adapter/bridge.py).

// Given whether the bridge joins the ports (`bridged`), whether each port is
// connected, and whether Find is looking for the screen (`finding`), returns:
//  - `choiceShown`: whether "Goes to" shows, offered while both ports are
//    connected;
//  - `choice`: the value Goes to shows, "simulator" or "screen";
//  - `typingDisabled`: whether the field, its boxes, and the buttons that
//    start the screen again are disabled. While joined, only the program on
//    the MCU port sends the screen instructions;
//  - `listsDisabled`: whether the lists of ports and rates are disabled.
//    While joined, connecting one port again at another rate would leave the
//    two ports at different rates;
//  - `findDisabled`: whether Find is disabled.
export function bridgeControls({ bridged, mcuConnected, screenConnected, finding }) {
  return {
    choiceShown: bridged || (mcuConnected && screenConnected),
    choice: bridged ? "screen" : "simulator",
    typingDisabled: bridged,
    listsDisabled: bridged,
    findDisabled: bridged || finding,
  };
}
