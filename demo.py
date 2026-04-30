"""
Demo for dearpygui_resizablechildwindow.

Shows both usage patterns:
  1. HSplit / VSplit — explicit split containers
  2. add_child_window / child_window — drop-in replacement for dpg equivalents
  3. patch_dpg() — monkey-patch so ALL dpg.add_child_window calls become resizable
"""
import dearpygui.dearpygui as dpg
from dearpygui_resizablechildwindow import HSplit, VSplit, child_window, patch_dpg

# Uncomment to make dpg.add_child_window / dpg.child_window globally resizable:
# patch_dpg()


def main() -> None:
    dpg.create_context()
    dpg.create_viewport(title="Resizable Child Window Demo", width=1000, height=700)
    dpg.setup_dearpygui()

    with dpg.window(tag="main"):

        dpg.add_text("── HSplit (drag the grey bar left/right) ──")
        h = HSplit(parent="main", ratio=0.4)
        for i in range(30):
            dpg.add_text(f"Left {i}", parent=h.left)
        for i in range(30):
            dpg.add_text(f"Right {i}", parent=h.right)

        dpg.add_spacer(height=8, parent="main")
        dpg.add_text("── VSplit (drag the grey bar up/down) ──", parent="main")
        v = VSplit(parent="main", ratio=0.5)
        for i in range(10):
            dpg.add_text(f"Top {i}", parent=v.top)
        for i in range(10):
            dpg.add_text(f"Bottom {i}", parent=v.bottom)

        dpg.add_spacer(height=8, parent="main")
        dpg.add_text(
            "── child_window() drop-in (drag the blue edges to resize) ──",
            parent="main",
        )
        with child_window(width=350, height=150, parent="main") as cw:
            dpg.add_text("This window has drag handles on the right and bottom edges.")
            dpg.add_text("Drag the grey (hover=blue) strips to resize it.")
            for i in range(20):
                dpg.add_text(f"  item {i}")

    dpg.show_viewport()
    dpg.set_primary_window("main", True)
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
