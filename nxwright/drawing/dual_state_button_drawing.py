"""Drawing a dual-state button: as a button is drawn, in its first look
while its `val` is 0, and in its second while it is 1, the look a button
shows while pressed: `bco2`, `pco2`, `pic2`, and `picc2` in place of `bco`,
`pco`, `pic`, and `picc`, and a `style` 4 sunk rather than raised. This
matched the Editor's simulator pixel for pixel
(tests/fixtures/value-widgets/).
"""


def paint_dual_state_button(painter):
    """Paints a dual-state button in the look its `val` chooses."""
    look = painter.second_look() if painter.values.get("val", 0) else painter
    look.text_component()
