from __future__ import annotations

import dearpygui.dearpygui as dpg


class _SplitBase:
    """Internal base for HSplit and VSplit.

    Manages themes, layout, and mouse/resize handlers shared by both orientations.
    Subclasses implement _avail_space, _apply_sizes, and orientation-specific
    _on_click/_on_drag overrides.
    """

    def __init__(
        self,
        parent: int | str,
        *,
        ratio: float = 0.5,
        min_pane_size: int = 20,
        divider_thickness: int = 6,
    ) -> None:
        """Set up state, build DPG items, and schedule initial sizing on frame 2.

        Args:
            parent: DearPyGUI tag of the containing window or group.
            ratio: Initial fraction of available space given to pane_a. Clamped to [0, 1].
            min_pane_size: Minimum pixel size for either pane.
            divider_thickness: Pixel width (HSplit) or height (VSplit) of the drag strip.
                Clamped to a minimum of 1.
        """
        self._parent = parent
        self._ratio = max(0.0, min(1.0, ratio))
        self._min = min_pane_size
        self._thickness = max(1, divider_thickness)
        self._total_w = 0
        self._total_h = 0
        self._dragging = False
        self._drag_start_a = 0
        self._is_hovered = False
        self._destroyed = False

        self._build_themes()
        self._build_layout(parent)
        self._register_handlers(parent)
        dpg.set_frame_callback(2, self._init_sizes)

    # ------------------------------------------------------------------ #
    # Setup                                                                 #
    # ------------------------------------------------------------------ #

    def _build_themes(self) -> None:
        """Create the three DPG themes used by the group and divider strip."""
        self._theme_group = dpg.add_theme()
        with dpg.theme_component(dpg.mvAll, parent=self._theme_group):
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)

        self._theme_divider = dpg.add_theme()
        with dpg.theme_component(dpg.mvChildWindow, parent=self._theme_divider):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (55, 55, 55, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Border, (55, 55, 55, 255))
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 0)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)

        self._theme_hover = dpg.add_theme()
        with dpg.theme_component(dpg.mvChildWindow, parent=self._theme_hover):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (90, 140, 220, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Border, (90, 140, 220, 255))
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 0)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)

    def _build_layout(self, parent: int | str) -> None:
        """Create the group, two panes, and the divider child_window."""
        self._group = dpg.add_group(
            parent=parent,
            horizontal=self._horizontal,
            horizontal_spacing=0,
        )
        dpg.bind_item_theme(self._group, self._theme_group)

        self._pane_a = dpg.add_child_window(
            parent=self._group,
            width=1,
            height=1,
            border=True,
        )
        self._divider = dpg.add_child_window(
            parent=self._group,
            width=self._thickness if self._horizontal else 1,
            height=1 if self._horizontal else self._thickness,
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        )
        dpg.bind_item_theme(self._divider, self._theme_divider)

        self._pane_b = dpg.add_child_window(
            parent=self._group,
            width=1,
            height=1,
            border=True,
        )

    def _register_handlers(self, parent: int | str) -> None:
        """Attach global mouse handlers and a per-parent resize handler."""
        self._registry = dpg.add_handler_registry()
        dpg.add_mouse_click_handler(
            dpg.mvMouseButton_Left,
            callback=self._on_click,
            parent=self._registry,
        )
        dpg.add_mouse_drag_handler(
            dpg.mvMouseButton_Left,
            threshold=1.0,
            callback=self._on_drag,
            parent=self._registry,
        )
        dpg.add_mouse_release_handler(
            dpg.mvMouseButton_Left,
            callback=self._on_release,
            parent=self._registry,
        )
        dpg.add_mouse_move_handler(
            callback=self._on_mouse_move,
            parent=self._registry,
        )

        self._parent_resize_registry = dpg.add_item_handler_registry()
        dpg.add_item_resize_handler(
            callback=self._on_parent_resize,
            parent=self._parent_resize_registry,
        )
        dpg.bind_item_handler_registry(parent, self._parent_resize_registry)

    # ------------------------------------------------------------------ #
    # Size management                                                       #
    # ------------------------------------------------------------------ #

    def _init_sizes(self, sender=None, app_data=None, user_data=None) -> None:
        """Read parent dimensions and call set_size; fired by set_frame_callback on frame 2."""
        size = dpg.get_item_rect_size(self._parent)
        w = size[0] or dpg.get_item_width(self._parent) or 100
        h = size[1] or dpg.get_item_height(self._parent) or 100
        self.set_size(w, h)

    def set_size(self, width: int, height: int) -> None:
        """Resize the split to fill the given dimensions, preserving the current ratio.

        Args:
            width: Total pixel width available (including divider).
            height: Total pixel height available (including divider).
        """
        if self._destroyed:
            return
        self._total_w = width
        self._total_h = height
        avail = self._avail_space()
        if avail <= 0:
            return
        new_a = max(self._min, min(avail - self._min, int(avail * self._ratio)))
        new_b = avail - new_a
        self._apply_sizes(new_a, new_b)

    def _avail_space(self) -> int:
        """Return the pixel space available to the two panes (total minus divider)."""
        raise NotImplementedError

    def _apply_sizes(self, a: int, b: int) -> None:
        """Set pane_a to *a* pixels and pane_b to *b* pixels along the split axis."""
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Callbacks                                                             #
    # ------------------------------------------------------------------ #

    def _on_parent_resize(self, sender: int, app_data: object, user_data=None) -> None:
        """DPG callback; fired when the parent window or pane is resized."""
        if self._destroyed:
            return
        size = dpg.get_item_rect_size(self._parent)
        w = size[0] or dpg.get_item_width(self._parent) or self._total_w
        h = size[1] or dpg.get_item_height(self._parent) or self._total_h
        self.set_size(w, h)

    def _on_click(self, sender: int, app_data: int, user_data=None) -> None:
        """DPG callback; starts a drag if the left button was pressed over the divider."""
        if self._destroyed:
            return
        if dpg.is_item_hovered(self._divider):
            self._dragging = True
            self._drag_start_a = (
                dpg.get_item_width(self._pane_a) if self._horizontal
                else dpg.get_item_height(self._pane_a)
            ) or int(self._avail_space() * self._ratio)

    def _on_drag(self, sender: int, app_data: list, user_data=None) -> None:
        """DPG callback; app_data = [button, cumulative_dx, cumulative_dy] from click origin."""
        if self._destroyed or not self._dragging:
            return
        delta = int(app_data[1])  # X delta; VSplit overrides to use app_data[2]
        avail = self._avail_space()
        if avail <= 0:
            return
        new_a = max(self._min, min(avail - self._min, self._drag_start_a + delta))
        self._ratio = new_a / avail
        self._apply_sizes(new_a, avail - new_a)

    def _on_release(self, sender: int, app_data: int, user_data=None) -> None:
        """DPG callback; clears drag state on left button release."""
        self._dragging = False

    def _on_mouse_move(self, sender: int, app_data: list, user_data=None) -> None:
        """DPG callback; updates divider hover colour and self-cleans if items are gone."""
        if self._destroyed:
            return
        if not dpg.does_item_exist(self._divider):
            self.destroy()
            return
        hovered = dpg.is_item_hovered(self._divider)
        if hovered != self._is_hovered:
            self._is_hovered = hovered
            dpg.bind_item_theme(
                self._divider,
                self._theme_hover if hovered else self._theme_divider,
            )

    # ------------------------------------------------------------------ #
    # Lifecycle                                                             #
    # ------------------------------------------------------------------ #

    def destroy(self) -> None:
        """Delete all DearPyGUI items owned by this split.

        Safe to call multiple times; subsequent calls are no-ops. After destroy()
        the instance must not be used.
        """
        if self._destroyed:
            return
        self._destroyed = True
        for tag in (
            self._registry,
            self._parent_resize_registry,
            self._theme_group,
            self._theme_divider,
            self._theme_hover,
            self._group,
        ):
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

    # ------------------------------------------------------------------ #
    # Properties                                                            #
    # ------------------------------------------------------------------ #

    @property
    def tag(self) -> int:
        """The outermost DearPyGUI item (the group container)."""
        return self._group


class HSplit(_SplitBase):
    """Left/right split pane with a draggable vertical divider.

    The split auto-resizes when the parent window is resized. Hover over the
    divider to highlight it blue; drag it to rebalance the two panes.

    Example::

        h = HSplit(parent="main", ratio=0.4)
        dpg.add_text("Left panel", parent=h.left)
        dpg.add_text("Right panel", parent=h.right)
    """

    _horizontal = True

    def __init__(
        self,
        parent: int | str,
        *,
        ratio: float = 0.5,
        min_pane_size: int = 20,
        divider_thickness: int = 6,
    ) -> None:
        """Create a left/right split with a draggable vertical divider.

        Args:
            parent: DearPyGUI tag of the containing window or group.
            ratio: Initial fraction of available width given to the left pane.
                Clamped to [0, 1]. Defaults to 0.5.
            min_pane_size: Minimum pixel width for either pane. Defaults to 20.
            divider_thickness: Width in pixels of the draggable divider strip.
                Defaults to 6.
        """
        super().__init__(
            parent,
            ratio=ratio,
            min_pane_size=min_pane_size,
            divider_thickness=divider_thickness,
        )

    def _avail_space(self) -> int:
        """Return total width minus divider thickness."""
        return self._total_w - self._thickness

    def _apply_sizes(self, a: int, b: int) -> None:
        """Set left pane to *a* px wide and right pane to *b* px wide."""
        dpg.set_item_width(self._pane_a, a)
        dpg.set_item_width(self._pane_b, b)
        for item in (self._pane_a, self._divider, self._pane_b):
            dpg.set_item_height(item, self._total_h)

    @property
    def left(self) -> int:
        """Tag of the left child_window pane."""
        return self._pane_a

    @property
    def right(self) -> int:
        """Tag of the right child_window pane."""
        return self._pane_b


class VSplit(_SplitBase):
    """Top/bottom split pane with a draggable horizontal divider.

    The split auto-resizes when the parent window is resized. Hover over the
    divider to highlight it blue; drag it to rebalance the two panes.

    Example::

        v = VSplit(parent="main", ratio=0.5)
        dpg.add_text("Top panel", parent=v.top)
        dpg.add_text("Bottom panel", parent=v.bottom)
    """

    _horizontal = False

    def __init__(
        self,
        parent: int | str,
        *,
        ratio: float = 0.5,
        min_pane_size: int = 20,
        divider_thickness: int = 6,
    ) -> None:
        """Create a top/bottom split with a draggable horizontal divider.

        Args:
            parent: DearPyGUI tag of the containing window or group.
            ratio: Initial fraction of available height given to the top pane.
                Clamped to [0, 1]. Defaults to 0.5.
            min_pane_size: Minimum pixel height for either pane. Defaults to 20.
            divider_thickness: Height in pixels of the draggable divider strip.
                Defaults to 6.
        """
        super().__init__(
            parent,
            ratio=ratio,
            min_pane_size=min_pane_size,
            divider_thickness=divider_thickness,
        )

    def _avail_space(self) -> int:
        """Return total height minus divider thickness."""
        return self._total_h - self._thickness

    def _apply_sizes(self, a: int, b: int) -> None:
        """Set top pane to *a* px tall and bottom pane to *b* px tall."""
        dpg.set_item_height(self._pane_a, a)
        dpg.set_item_height(self._pane_b, b)
        for item in (self._pane_a, self._divider, self._pane_b):
            dpg.set_item_width(item, self._total_w)

    def _on_drag(self, sender: int, app_data: list, user_data=None) -> None:
        """DPG callback; uses Y delta (app_data[2]) instead of X."""
        if self._destroyed or not self._dragging:
            return
        delta = int(app_data[2])  # Y delta
        avail = self._avail_space()
        if avail <= 0:
            return
        new_a = max(self._min, min(avail - self._min, self._drag_start_a + delta))
        self._ratio = new_a / avail
        self._apply_sizes(new_a, avail - new_a)

    def _on_click(self, sender: int, app_data: int, user_data=None) -> None:
        """DPG callback; reads top pane height (not width) at drag start."""
        if self._destroyed:
            return
        if dpg.is_item_hovered(self._divider):
            self._dragging = True
            self._drag_start_a = (
                dpg.get_item_height(self._pane_a)
                or int(self._avail_space() * self._ratio)
            )

    @property
    def top(self) -> int:
        """Tag of the top child_window pane."""
        return self._pane_a

    @property
    def bottom(self) -> int:
        """Tag of the bottom child_window pane."""
        return self._pane_b
