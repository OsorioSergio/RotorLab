# View Cube Icon Slots

Drop optional `svg` or `png` files in this folder to override the procedural
viewport widget icons.

Supported control names:

- `home`
- `roll_left`
- `roll_right`
- `rotate_up`
- `rotate_down`
- `rotate_left`
- `rotate_right`

Supported filenames:

- `<control>.svg`
- `<control>.png`

Examples:

- `home.svg`
- `rotate_up.png`
- `roll_left.svg`

Behavior:

- If an icon file exists, the widget will render that image for the matching
  control.
- If no icon file exists, the widget falls back to the built-in `QPainter`
  placeholder glyph.
- `svg` is checked before `png`.

Recommendations:

- Use a transparent background.
- Keep artwork centered in a square canvas.
- Prefer light icons because the viewport background is dark.
