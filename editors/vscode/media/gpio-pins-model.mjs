// The GPIO pins as the Simulator section lists them (simulator-controls.mjs),
// from what the simulation sends of them (nxwright/gpio): each pin's mode,
// the component a bound pin presses, and its level. An input's level is a
// button, which gives the pin the other level, as a switch wired to it would.

// What each of cfgpio's modes makes a pin, as the section says it.
const KINDS = ["input", "input", "output", "PWM output", "open-drain output"];
const BOUND = 1;
const PWM = 3;

// Returns a row for each pin, by pin number: its `name`, what it is
// (`kind`), its `level`, or null for a PWM output, whose level changes too
// fast to show, whether a click changes it (`settable`), and the click's
// tooltip (`title`).
export function pinRows(pins) {
  return pins.map((pin, number) => {
    const name = `io${number}`;
    const settable = pin.mode <= BOUND;
    const bound = pin.mode === BOUND && pin.component !== null;
    let title;
    if (settable) {
      const next = 1 - pin.level;
      // A falling level presses the bound component, and a rising one releases it.
      const runs = !bound ? "" : `, which ${next === 0 ? "presses" : "releases"} ${pin.component}`;
      title = `Set ${name} to ${next}${runs}`;
    }
    return {
      name,
      kind: bound ? `input, bound to ${pin.component}` : KINDS[pin.mode],
      level: pin.mode === PWM ? null : pin.level,
      settable,
      title,
    };
  });
}
