"""
Headless smoke tests — no display required.
Run with: uv run python test_smoke.py
"""
import dearpygui.dearpygui as dpg
from dearpygui_resizablechildwindow import add_child_window, child_window, patch_dpg, HSplit, VSplit
from dearpygui_resizablechildwindow._wrapper import _instances

dpg.create_context()
with dpg.window(tag="win", width=800, height=600):
    pass


# ── 1. add_child_window with both handles ──────────────────────────────────
cw = add_child_window(width=300, height=200, parent="win")
assert dpg.does_item_exist(cw), "content window should exist"
dpg.add_text("hello", parent=cw)  # adding content must not crash
print("1. add_child_window (both handles) OK")

# ── 2. X-only resize ──────────────────────────────────────────────────────
cw2 = add_child_window(width=300, height=200, resizable_x=True, resizable_y=False, parent="win")
assert dpg.does_item_exist(cw2)
print("2. resizable_x only OK")

# ── 3. width=0 / height=0 falls through to plain dpg.add_child_window ────
cw3 = add_child_window(width=0, height=0, parent="win")
assert dpg.get_item_type(cw3) == "mvAppItemType::mvChildWindow"
assert cw3 not in _instances, "auto-size windows must not be in _instances"
print("3. width=0, height=0 passthrough OK")

# ── 4. explicit tag is honoured ───────────────────────────────────────────
cw4 = add_child_window(tag="my_panel", width=200, height=150, parent="win")
assert dpg.does_item_exist("my_panel"), "explicit tag must be registered"
assert cw4 == "my_panel" or dpg.does_item_exist(cw4)
dpg.add_text("tagged content", parent="my_panel")
print("4. explicit tag OK")

# ── 5. child_window context manager ──────────────────────────────────────
with child_window(width=250, height=120, parent="win") as cw5:
    dpg.add_text("inside context manager")
assert dpg.does_item_exist(cw5)
print("5. child_window context manager OK")

# ── 6. resize drag logic ──────────────────────────────────────────────────
impl = _instances[cw]
impl._drag_x = True
impl._drag_y = True
impl._start_w = impl._cur_w
impl._start_h = impl._cur_h
impl._on_drag(0, [0, 50, 30])
expected_w = (300 - 6) + 50  # content_w + delta
expected_h = (200 - 6) + 30
assert impl._cur_w == expected_w, f"got {impl._cur_w}, want {expected_w}"
assert impl._cur_h == expected_h, f"got {impl._cur_h}, want {expected_h}"
assert dpg.get_item_width(cw)  == expected_w
assert dpg.get_item_height(cw) == expected_h
print(f"6. drag +50x +30y → content is {impl._cur_w}x{impl._cur_h} OK")

# ── 7. minimum size clamping ──────────────────────────────────────────────
impl._drag_x = True
impl._drag_y = True
impl._start_w = impl._cur_w
impl._start_h = impl._cur_h
impl._on_drag(0, [0, -999999, -999999])
assert impl._cur_w == 20, f"min_w clamp failed, got {impl._cur_w}"
assert impl._cur_h == 20, f"min_h clamp failed, got {impl._cur_h}"
print("7. minimum-size clamp OK")

# ── 8. release resets drag flags ─────────────────────────────────────────
impl._on_release(0, 0)
assert not impl._drag_x
assert not impl._drag_y
print("8. release resets drag flags OK")

# ── 9. HSplit set_size preserves ratio ───────────────────────────────────
h = HSplit(parent="win", ratio=0.4)
h.set_size(800, 400)
left_w  = dpg.get_item_width(h.left)
right_w = dpg.get_item_width(h.right)
avail = 800 - 6
assert left_w  == max(20, min(avail - 20, int(avail * 0.4))), f"left_w={left_w}"
assert left_w + right_w == avail, f"{left_w} + {right_w} != {avail}"
print(f"9. HSplit set_size ratio=0.4 → {left_w}/{right_w} OK")

# ── 10. VSplit drag uses Y delta ──────────────────────────────────────────
v = VSplit(parent="win", ratio=0.5)
v.set_size(400, 300)
v._dragging = True
v._drag_start_a = dpg.get_item_height(v.top)
v._on_drag(0, [0, 999, -40])          # X ignored, Y = -40 → top shrinks
top_h = dpg.get_item_height(v.top)
assert top_h == v._drag_start_a - 40, f"top_h={top_h}"
print(f"10. VSplit drag Y=-40 → top={top_h} OK")

# ── 11. patch_dpg replaces dpg symbols ───────────────────────────────────
patch_dpg()
import dearpygui.dearpygui as _dpg
assert _dpg.add_child_window is add_child_window
assert _dpg.child_window     is child_window
print("11. patch_dpg OK")

# ── 12. destroy cleans up handler registry, themes, and outer group ──────
# Use a fresh window so nothing is bound to impl's themes from earlier tests.
cw_d = add_child_window(width=200, height=150, parent="win")
impl_d = _instances[cw_d]
reg_d = impl_d._registry
tn_d  = impl_d._theme_normal
th_d  = impl_d._theme_hover
outer_d = impl_d._outer
impl_d.destroy()
assert not dpg.does_item_exist(reg_d),   "registry should be deleted"
assert not dpg.does_item_exist(tn_d),    "theme_normal should be deleted"
assert not dpg.does_item_exist(th_d),    "theme_hover should be deleted"
assert not dpg.does_item_exist(outer_d), "outer group should be deleted"
assert cw_d not in _instances,           "should be removed from _instances"
print("12. destroy() cleanup OK")

dpg.destroy_context()
print("\nAll smoke tests passed.")
