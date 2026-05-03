import dearpygui.dearpygui as dpg
import dearpygui.demo as demo
from dearpygui_resizablechildwindow import patch_dpg

patch_dpg()

dpg.create_context()
dpg.create_viewport(title="DearPyGUI + Resizable Child Windows", width=1280, height=800)
dpg.setup_dearpygui()

demo.show_demo()

dpg.show_about()
dpg.show_debug()
dpg.show_documentation()
dpg.show_font_manager()
dpg.show_item_registry()
dpg.show_metrics()
dpg.show_style_editor()
dpg.show_imgui_demo()
dpg.show_implot_demo()

dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()
