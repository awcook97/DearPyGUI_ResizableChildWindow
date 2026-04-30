# Resizeable DearPyGUI Child Windows

I was getting annoyed that my child windows weren't resizeable, so I decided to make them ALL resizeable by monkey-patching the `add_child_window` function. 

## Installation

```bash
pip install dearpygui-resizablechildwindow
```

Requires Python 3.14+ and DearPyGUI 2.3+.

---

## Usage

### Drop-in replacement (easiest)

Call `patch_dpg()` once at startup. Every `dpg.add_child_window` and `dpg.child_window`
call in your entire codebase gains drag handles automatically — no other changes needed.

```python
import dearpygui.dearpygui as dpg
import dearpygui_resizablechildwindow

dearpygui_resizablechildwindow.patch_dpg()

dpg.create_context()
dpg.create_viewport(title="My App", width=900, height=600)
dpg.setup_dearpygui()

with dpg.window(tag="main"):
    # Now resizable by default — drag the grey strip on the right/bottom edges
    with dpg.child_window(width=400, height=300) as cw:
        dpg.add_text("Drag the right or bottom edge to resize me")

dpg.show_viewport()
dpg.set_primary_window("main", True)
dpg.start_dearpygui()
dpg.destroy_context()
```

To opt a specific window **out** of resizing, pass `resizable_x=False, resizable_y=False`:

```python
with dpg.child_window(width=200, height=100, resizable_x=False, resizable_y=False):
    dpg.add_text("Fixed size, no handles")
```

---

### Explicit import (selective use)

```python
from dearpygui_resizablechildwindow import add_child_window, child_window

# Function style
cw = add_child_window(width=300, height=200, parent="main")
dpg.add_text("content", parent=cw)

# Context manager style
with child_window(width=300, height=200, parent="main") as cw:
    dpg.add_text("content")
```

Both functions accept every parameter that `dpg.add_child_window` accepts, plus two extras:

| Extra param | Default | Description |
|-------------|---------|-------------|
| `min_width` | `20` | Minimum content width when dragging |
| `min_height` | `20` | Minimum content height when dragging |

The only default that changes from stock DearPyGUI: `resizable_x` and `resizable_y` are
`True` here (they default to `False` in DearPyGUI).

When `width=0` or `height=0` (auto-size), that axis falls back to DearPyGUI's native
`resizable_x`/`resizable_y` flag instead of adding a custom handle.

---

### Split panes

`HSplit` and `VSplit` give you two panes with a draggable divider between them. They
auto-resize when the host window is resized.

```python
from dearpygui_resizablechildwindow import HSplit, VSplit

with dpg.window(tag="main"):
    # Left / right split, starting at 40% left
    h = HSplit(parent="main", ratio=0.4)
    dpg.add_text("Left panel", parent=h.left)
    dpg.add_text("Right panel", parent=h.right)

    # Top / bottom split
    v = VSplit(parent="main", ratio=0.5)
    dpg.add_text("Top panel", parent=v.top)
    dpg.add_text("Bottom panel", parent=v.bottom)
```

**Constructor parameters** (same for both):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `parent` | required | DearPyGUI tag of the containing window or pane |
| `ratio` | `0.5` | Initial size of the first pane as a fraction of available space |
| `min_pane_size` | `20` | Minimum pixel size for either pane |

**Properties:**
- `h.left`, `h.right` — DearPyGUI tags for the left and right panes
- `v.top`, `v.bottom` — DearPyGUI tags for the top and bottom panes
- `.tag` — tag of the outermost group item (useful for nesting)

**Methods:**
- `.set_size(width, height)` — manually update total dimensions (called automatically on parent resize)
- `.destroy()` — clean up all DearPyGUI items owned by this split

Splits resize proportionally when their parent window is resized. Hover over the divider
to see it highlight blue; drag to resize.

---

## How it works

- A 6 px `child_window` strip is placed alongside your content window inside a zero-spacing
  group. Dragging the strip updates the content window's width/height via
  `dpg.set_item_width` / `dpg.set_item_height`.
- Drag state is tracked with `dpg.add_mouse_click_handler` + `dpg.is_item_hovered` at click
  time, then `dpg.add_mouse_drag_handler` for cumulative deltas.
- Parent resize is detected with `dpg.add_item_resize_handler` (works on both
  `mvWindowAppItem` and `mvChildWindow` in DearPyGUI 2.3).

---

## License
I'll get GitHub to add a license here after publishing to GitHub and eventually to PyPI. For now, just assume it's MIT or something. IDC what you use it for, it was 2 shot vibe coded anyways.
