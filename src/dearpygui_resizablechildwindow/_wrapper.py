"""
Drop-in replacement for dpg.add_child_window / dpg.child_window that adds
visible drag handles on the right and/or bottom edges.

Usage — identical to the originals:

    from dearpygui_resizablechildwindow import add_child_window, child_window

    # function style
    cw = add_child_window(width=300, height=200)
    dpg.add_text("hello", parent=cw)

    # context manager style
    with child_window(width=300, height=200) as cw:
        dpg.add_text("hello")

    # monkey-patch dpg so all existing code becomes resizable:
    from dearpygui_resizablechildwindow import patch_dpg
    patch_dpg()

Key differences from dpg.add_child_window:
  - resizable_x defaults to True  (was False)
  - resizable_y defaults to True  (was False)
  - Adds extra keyword-only args: min_width (default 20), min_height (default 20),
    handle_thickness (default 6)
  - When resizable_x=True and width>0, a drag handle is added to the right
  - When resizable_y=True and height>0, a drag handle is added to the bottom
  - If both, a corner handle allows simultaneous resize
  - When width=0 or height=0 (auto-size), that axis falls back to native resizable_x/y
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Generator, List, Tuple, Union

import dearpygui.dearpygui as dpg

_MIN = 20  # default minimum content dimension

# Capture the real dpg function before patch_dpg() can replace it.
# All internal calls must go through this reference to avoid infinite recursion.
_dpg_add_child_window = dpg.add_child_window

# Module-level registry keeps _ResizableWindowImpl alive (prevents GC of callbacks).
# Keyed by content child_window tag. Cleaned up when destroy() is called.
_instances: dict[int | str, _ResizableWindowImpl] = {}


# --------------------------------------------------------------------------- #
# Internal implementation                                                       #
# --------------------------------------------------------------------------- #

class _ResizableWindowImpl:
    """Manages drag handles and resize callbacks for one resizable child_window.

    Owns all DPG handler and theme items it creates. Call destroy() to clean up,
    or let _on_mouse_move self-clean when the content window is deleted externally.
    """

    def __init__(
        self,
        content: int | str,
        outer_group: int,
        right_handle: int | None,
        bottom_handle: int | None,
        corner_handle: int | None,
        init_w: int,
        init_h: int,
        min_w: int,
        min_h: int,
    ) -> None:
        """Attach themes and mouse handlers to the given set of DPG items.

        Args:
            content: Tag of the user-visible content child_window.
            outer_group: Tag of the outermost group that owns all layout items.
                Deleting this cascades to all handles, releasing theme bindings.
            right_handle: Tag of the right-edge drag strip, or None.
            bottom_handle: Tag of the bottom-edge drag strip, or None.
            corner_handle: Tag of the corner drag square (both axes), or None.
            init_w: Initial content width in pixels.
            init_h: Initial content height in pixels.
            min_w: Minimum content width when dragging.
            min_h: Minimum content height when dragging.
        """
        self._content       = content
        self._outer         = outer_group
        self._right         = right_handle
        self._bottom        = bottom_handle
        self._corner        = corner_handle
        self._cur_w         = init_w
        self._cur_h         = init_h
        self._min_w         = min_w
        self._min_h         = min_h
        self._drag_x        = False
        self._drag_y        = False
        self._start_w       = 0
        self._start_h       = 0
        self._hovered: dict[int, bool] = {}
        self._destroyed     = False

        self._build_themes()
        for h in self._handles:
            dpg.bind_item_theme(h, self._theme_normal)
        self._register_handlers()

    @property
    def _handles(self) -> list[int]:
        """Non-None handle tags as a flat list."""
        return [h for h in (self._right, self._bottom, self._corner) if h is not None]

    # ------------------------------------------------------------------ #
    # Themes                                                                #
    # ------------------------------------------------------------------ #

    def _build_themes(self) -> None:
        """Create the normal (grey) and hover (blue) themes for the drag handles."""
        self._theme_normal = dpg.add_theme()
        with dpg.theme_component(dpg.mvChildWindow, parent=self._theme_normal):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (55, 55, 55, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Border,  (55, 55, 55, 255))
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 0)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,   0, 0)

        self._theme_hover = dpg.add_theme()
        with dpg.theme_component(dpg.mvChildWindow, parent=self._theme_hover):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (90, 140, 220, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Border,  (90, 140, 220, 255))
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 0)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,   0, 0)

    # ------------------------------------------------------------------ #
    # Handlers                                                              #
    # ------------------------------------------------------------------ #

    def _register_handlers(self) -> None:
        """Create the global mouse handler registry and attach all callbacks."""
        self._registry = dpg.add_handler_registry()
        dpg.add_mouse_click_handler(
            dpg.mvMouseButton_Left, callback=self._on_click, parent=self._registry,
        )
        dpg.add_mouse_drag_handler(
            dpg.mvMouseButton_Left, threshold=1.0, callback=self._on_drag, parent=self._registry,
        )
        dpg.add_mouse_release_handler(
            dpg.mvMouseButton_Left, callback=self._on_release, parent=self._registry,
        )
        dpg.add_mouse_move_handler(callback=self._on_mouse_move, parent=self._registry)

    def _on_click(self, sender: int, app_data: int, user_data=None) -> None:
        """DPG callback; records which axes to drag based on which handle was hovered."""
        if self._destroyed:
            return
        right_hov  = self._right  is not None and bool(dpg.is_item_hovered(self._right))
        bottom_hov = self._bottom is not None and bool(dpg.is_item_hovered(self._bottom))
        corner_hov = self._corner is not None and bool(dpg.is_item_hovered(self._corner))

        if right_hov or corner_hov:
            self._drag_x = True
            self._start_w = dpg.get_item_width(self._content) or self._cur_w
        if bottom_hov or corner_hov:
            self._drag_y = True
            self._start_h = dpg.get_item_height(self._content) or self._cur_h

    def _on_drag(self, sender: int, app_data: list, user_data=None) -> None:
        """DPG callback; app_data = [button, cumulative_dx, cumulative_dy] from click origin."""
        if self._destroyed or not (self._drag_x or self._drag_y):
            return

        if self._drag_x:
            new_w = max(self._min_w, self._start_w + int(app_data[1]))
            if new_w != self._cur_w:
                self._cur_w = new_w
                dpg.set_item_width(self._content, new_w)
                if self._bottom is not None:
                    dpg.set_item_width(self._bottom, new_w)

        if self._drag_y:
            new_h = max(self._min_h, self._start_h + int(app_data[2]))
            if new_h != self._cur_h:
                self._cur_h = new_h
                dpg.set_item_height(self._content, new_h)
                if self._right is not None:
                    dpg.set_item_height(self._right, new_h)

    def _on_release(self, sender: int, app_data: int, user_data=None) -> None:
        """DPG callback; clears drag state on left button release."""
        self._drag_x = False
        self._drag_y = False

    def _on_mouse_move(self, sender: int, app_data: list, user_data=None) -> None:
        """DPG callback; updates handle hover colours and self-cleans if items are gone."""
        if self._destroyed:
            return
        if not dpg.does_item_exist(self._content):
            self.destroy()
            return
        for handle in self._handles:
            hovered = bool(dpg.is_item_hovered(handle))
            if hovered != self._hovered.get(handle, False):
                self._hovered[handle] = hovered
                dpg.bind_item_theme(
                    handle, self._theme_hover if hovered else self._theme_normal
                )

    # ------------------------------------------------------------------ #
    # Lifecycle                                                             #
    # ------------------------------------------------------------------ #

    def destroy(self) -> None:
        """Delete all DPG items owned by this instance and remove it from _instances."""
        if self._destroyed:
            return
        self._destroyed = True
        _instances.pop(self._content, None)
        # Delete the outer group first — this cascades to all handle child_windows,
        # which releases their theme bindings. Themes can then be deleted safely.
        if dpg.does_item_exist(self._outer):
            dpg.delete_item(self._outer)
        for tag in (self._registry, self._theme_normal, self._theme_hover):
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)


# --------------------------------------------------------------------------- #
# Zero-spacing group theme (shared, created lazily)                            #
# --------------------------------------------------------------------------- #

_spacing_theme: int | None = None


def _get_spacing_theme() -> int:
    """Return (creating if needed) the shared zero-spacing group theme."""
    global _spacing_theme
    if _spacing_theme is None or not dpg.does_item_exist(_spacing_theme):
        _spacing_theme = dpg.add_theme()
        with dpg.theme_component(dpg.mvAll, parent=_spacing_theme):
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
    return _spacing_theme


# --------------------------------------------------------------------------- #
# Public API                                                                    #
# --------------------------------------------------------------------------- #

def add_child_window(
    *,
    label:                  str                         = None,
    user_data:              Any                         = None,
    use_internal_label:     bool                        = True,
    tag:                    Union[int, str]             = 0,
    width:                  int                         = 0,
    height:                 int                         = 0,
    indent:                 int                         = -1,
    parent:                 Union[int, str]             = 0,
    before:                 Union[int, str]             = 0,
    payload_type:           str                         = '$$DPG_PAYLOAD',
    drop_callback:          Callable                    = None,
    show:                   bool                        = True,
    pos:                    Union[List[int], Tuple[int, ...]] = [],
    filter_key:             str                         = '',
    tracked:                bool                        = False,
    track_offset:           float                       = 0.5,
    border:                 bool                        = True,
    autosize_x:             bool                        = False,
    autosize_y:             bool                        = False,
    no_scrollbar:           bool                        = False,
    horizontal_scrollbar:   bool                        = False,
    menubar:                bool                        = False,
    no_scroll_with_mouse:   bool                        = False,
    flattened_navigation:   bool                        = True,
    always_use_window_padding: bool                     = False,
    resizable_x:            bool                        = True,
    resizable_y:            bool                        = True,
    always_auto_resize:     bool                        = False,
    frame_style:            bool                        = False,
    auto_resize_x:          bool                        = False,
    auto_resize_y:          bool                        = False,
    min_width:              int                         = _MIN,
    min_height:             int                         = _MIN,
    handle_thickness:       int                         = 6,
    **kwargs,
) -> Union[int, str]:
    """Drop-in for dpg.add_child_window() that adds visible drag-resize handles.

    Accepts every parameter that dpg.add_child_window accepts, plus three extras:
    min_width, min_height, and handle_thickness. The only defaults that differ
    from stock DearPyGUI are resizable_x and resizable_y (both True here vs False
    in DPG).

    When width=0 or height=0 (auto-size mode), that axis falls back to DPG's
    native resizable_x/resizable_y flag rather than adding a custom handle.

    Args:
        label: Optional label shown in DPG's item registry.
        user_data: Arbitrary data stored on the item; passed to callbacks.
        use_internal_label: If True, DPG manages the label string internally.
        tag: Explicit integer or string tag. Auto-generated if 0.
        width: Content width in pixels. 0 = auto-size (no custom X handle added).
        height: Content height in pixels. 0 = auto-size (no custom Y handle added).
        indent: Horizontal indent in pixels. -1 = no indent.
        parent: Tag of the parent container. 0 = current container stack top.
        before: Tag of the sibling item to insert before. 0 = append.
        payload_type: Drag-and-drop payload type string.
        drop_callback: Callback fired when a payload is dropped onto this window.
        show: If False, the item is hidden.
        pos: [x, y] absolute position. Empty list = layout-driven position.
        filter_key: String used by DPG filter widgets.
        tracked: If True, DPG keeps this item scrolled into view.
        track_offset: Vertical alignment when tracked (0.0 = top, 1.0 = bottom).
        border: Draw a border around the content window.
        autosize_x: Expand width to fit content automatically.
        autosize_y: Expand height to fit content automatically.
        no_scrollbar: Hide the scrollbar.
        horizontal_scrollbar: Show a horizontal scrollbar.
        menubar: Reserve space for a menu bar inside the window.
        no_scroll_with_mouse: Disable mouse-wheel scrolling.
        flattened_navigation: Keyboard/gamepad navigation crosses window boundaries.
        always_use_window_padding: Apply window padding even when border=False.
        resizable_x: Add a right-edge drag handle (when width > 0). Defaults to True.
        resizable_y: Add a bottom-edge drag handle (when height > 0). Defaults to True.
        always_auto_resize: Always resize to fit content (DPG native flag).
        frame_style: Draw a frame-style border.
        auto_resize_x: DPG native auto-resize flag for X.
        auto_resize_y: DPG native auto-resize flag for Y.
        min_width: Minimum content width when dragging. Defaults to 20.
        min_height: Minimum content height when dragging. Defaults to 20.
        handle_thickness: Pixel thickness of the drag handle strips. Defaults to 6.
        **kwargs: Additional keyword arguments forwarded to dpg.add_child_window.

    Returns:
        The DPG tag of the content child_window (same as *tag* if one was provided).

    Example::

        cw = add_child_window(width=300, height=200, parent="main")
        dpg.add_text("content", parent=cw)
    """
    has_x = resizable_x and width  > 0
    has_y = resizable_y and height > 0

    native_rx = resizable_x and not has_x
    native_ry = resizable_y and not has_y

    if not has_x and not has_y:
        return _dpg_add_child_window(
            label=label, user_data=user_data, use_internal_label=use_internal_label,
            tag=tag, width=width, height=height, indent=indent,
            parent=parent, before=before, payload_type=payload_type,
            drop_callback=drop_callback, show=show, pos=pos,
            filter_key=filter_key, tracked=tracked, track_offset=track_offset,
            border=border, autosize_x=autosize_x, autosize_y=autosize_y,
            no_scrollbar=no_scrollbar, horizontal_scrollbar=horizontal_scrollbar,
            menubar=menubar, no_scroll_with_mouse=no_scroll_with_mouse,
            flattened_navigation=flattened_navigation,
            always_use_window_padding=always_use_window_padding,
            resizable_x=native_rx, resizable_y=native_ry,
            always_auto_resize=always_auto_resize, frame_style=frame_style,
            auto_resize_x=auto_resize_x, auto_resize_y=auto_resize_y,
            **kwargs,
        )

    # --- Build the outer layout group ---------------------------------- #
    ht = max(1, handle_thickness)
    content_w = (width  - ht) if has_x else width
    content_h = (height - ht) if has_y else height

    outer_kwargs: dict[str, Any] = {}
    if parent:
        outer_kwargs['parent'] = parent
    if before:
        outer_kwargs['before'] = before
    if indent != -1:
        outer_kwargs['indent'] = indent
    if pos:
        outer_kwargs['pos'] = list(pos)
    if not show:
        outer_kwargs['show'] = show

    outer = dpg.add_group(horizontal=False, **outer_kwargs)
    dpg.bind_item_theme(outer, _get_spacing_theme())

    # Row 1: content window + optional right handle
    row1 = dpg.add_group(parent=outer, horizontal=True, horizontal_spacing=0)

    content_tag = tag if tag else dpg.generate_uuid()
    content = _dpg_add_child_window(
        tag=content_tag,
        parent=row1,
        label=label,
        user_data=user_data,
        use_internal_label=use_internal_label,
        width=content_w,
        height=content_h,
        payload_type=payload_type,
        drop_callback=drop_callback,
        filter_key=filter_key,
        tracked=tracked,
        track_offset=track_offset,
        border=border,
        autosize_x=autosize_x,
        autosize_y=autosize_y,
        no_scrollbar=no_scrollbar,
        horizontal_scrollbar=horizontal_scrollbar,
        menubar=menubar,
        no_scroll_with_mouse=no_scroll_with_mouse,
        flattened_navigation=flattened_navigation,
        always_use_window_padding=always_use_window_padding,
        resizable_x=native_rx,
        resizable_y=native_ry,
        always_auto_resize=always_auto_resize,
        frame_style=frame_style,
        auto_resize_x=auto_resize_x,
        auto_resize_y=auto_resize_y,
        **kwargs,
    )

    right_handle: int | None = None
    if has_x:
        right_handle = _dpg_add_child_window(
            parent=row1,
            width=ht,
            height=content_h,
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        )

    # Row 2: optional bottom handle + corner
    bottom_handle: int | None = None
    corner_handle: int | None = None
    if has_y:
        row2 = dpg.add_group(parent=outer, horizontal=True, horizontal_spacing=0)
        bottom_handle = _dpg_add_child_window(
            parent=row2,
            width=content_w,
            height=ht,
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        )
        if has_x:
            corner_handle = _dpg_add_child_window(
                parent=row2,
                width=ht,
                height=ht,
                border=False,
                no_scrollbar=True,
                no_scroll_with_mouse=True,
            )

    impl = _ResizableWindowImpl(
        content=content,
        outer_group=outer,
        right_handle=right_handle,
        bottom_handle=bottom_handle,
        corner_handle=corner_handle,
        init_w=content_w,
        init_h=content_h,
        min_w=min_width,
        min_h=min_height,
    )
    _instances[content] = impl

    return content


@contextmanager
def child_window(
    *,
    label:                  str                         = None,
    user_data:              Any                         = None,
    use_internal_label:     bool                        = True,
    tag:                    Union[int, str]             = 0,
    width:                  int                         = 0,
    height:                 int                         = 0,
    indent:                 int                         = -1,
    parent:                 Union[int, str]             = 0,
    before:                 Union[int, str]             = 0,
    payload_type:           str                         = '$$DPG_PAYLOAD',
    drop_callback:          Callable                    = None,
    show:                   bool                        = True,
    pos:                    Union[List[int], Tuple[int, ...]] = [],
    filter_key:             str                         = '',
    tracked:                bool                        = False,
    track_offset:           float                       = 0.5,
    border:                 bool                        = True,
    autosize_x:             bool                        = False,
    autosize_y:             bool                        = False,
    no_scrollbar:           bool                        = False,
    horizontal_scrollbar:   bool                        = False,
    menubar:                bool                        = False,
    no_scroll_with_mouse:   bool                        = False,
    flattened_navigation:   bool                        = True,
    always_use_window_padding: bool                     = False,
    resizable_x:            bool                        = True,
    resizable_y:            bool                        = True,
    always_auto_resize:     bool                        = False,
    frame_style:            bool                        = False,
    auto_resize_x:          bool                        = False,
    auto_resize_y:          bool                        = False,
    min_width:              int                         = _MIN,
    min_height:             int                         = _MIN,
    handle_thickness:       int                         = 6,
    **kwargs,
) -> Generator[Union[int, str], None, None]:
    """Context-manager drop-in for dpg.child_window(); yields the content pane tag.

    Accepts every parameter that dpg.child_window accepts, plus min_width,
    min_height, and handle_thickness. See add_child_window for full parameter docs.

    Args:
        label: Optional label shown in DPG's item registry.
        user_data: Arbitrary data stored on the item; passed to callbacks.
        use_internal_label: If True, DPG manages the label string internally.
        tag: Explicit integer or string tag. Auto-generated if 0.
        width: Content width in pixels. 0 = auto-size (no custom X handle).
        height: Content height in pixels. 0 = auto-size (no custom Y handle).
        indent: Horizontal indent in pixels. -1 = no indent.
        parent: Tag of the parent container. 0 = current container stack top.
        before: Tag of the sibling item to insert before. 0 = append.
        payload_type: Drag-and-drop payload type string.
        drop_callback: Callback fired when a payload is dropped onto this window.
        show: If False, the item is hidden.
        pos: [x, y] absolute position. Empty list = layout-driven position.
        filter_key: String used by DPG filter widgets.
        tracked: If True, DPG keeps this item scrolled into view.
        track_offset: Vertical alignment when tracked (0.0 = top, 1.0 = bottom).
        border: Draw a border around the content window.
        autosize_x: Expand width to fit content automatically.
        autosize_y: Expand height to fit content automatically.
        no_scrollbar: Hide the scrollbar.
        horizontal_scrollbar: Show a horizontal scrollbar.
        menubar: Reserve space for a menu bar inside the window.
        no_scroll_with_mouse: Disable mouse-wheel scrolling.
        flattened_navigation: Keyboard/gamepad navigation crosses window boundaries.
        always_use_window_padding: Apply window padding even when border=False.
        resizable_x: Add a right-edge drag handle (when width > 0). Defaults to True.
        resizable_y: Add a bottom-edge drag handle (when height > 0). Defaults to True.
        always_auto_resize: Always resize to fit content (DPG native flag).
        frame_style: Draw a frame-style border.
        auto_resize_x: DPG native auto-resize flag for X.
        auto_resize_y: DPG native auto-resize flag for Y.
        min_width: Minimum content width when dragging. Defaults to 20.
        min_height: Minimum content height when dragging. Defaults to 20.
        handle_thickness: Pixel thickness of the drag handle strips. Defaults to 6.
        **kwargs: Additional keyword arguments forwarded to dpg.add_child_window.

    Yields:
        The DPG tag of the content child_window. Items added inside the ``with``
        block are parented to this window automatically via the container stack.

    Example::

        with child_window(width=300, height=200, parent="main") as cw:
            dpg.add_text("content")
    """
    widget = add_child_window(
        label=label, user_data=user_data, use_internal_label=use_internal_label,
        tag=tag, width=width, height=height, indent=indent,
        parent=parent, before=before, payload_type=payload_type,
        drop_callback=drop_callback, show=show, pos=pos,
        filter_key=filter_key, tracked=tracked, track_offset=track_offset,
        border=border, autosize_x=autosize_x, autosize_y=autosize_y,
        no_scrollbar=no_scrollbar, horizontal_scrollbar=horizontal_scrollbar,
        menubar=menubar, no_scroll_with_mouse=no_scroll_with_mouse,
        flattened_navigation=flattened_navigation,
        always_use_window_padding=always_use_window_padding,
        resizable_x=resizable_x, resizable_y=resizable_y,
        always_auto_resize=always_auto_resize, frame_style=frame_style,
        auto_resize_x=auto_resize_x, auto_resize_y=auto_resize_y,
        min_width=min_width, min_height=min_height,
        handle_thickness=handle_thickness,
        **kwargs,
    )
    dpg.push_container_stack(widget)
    try:
        yield widget
    finally:
        dpg.pop_container_stack()


def patch_dpg() -> None:
    """Monkey-patch dearpygui so all child windows automatically gain resize handles.

    Call once at app startup, before creating any child windows.

    After this call, dpg.add_child_window and dpg.child_window are replaced with
    the resizable versions from this module. All existing code gains drag handles
    without any other changes.

    Example::

        import dearpygui_resizablechildwindow
        dearpygui_resizablechildwindow.patch_dpg()
        # All subsequent dpg.add_child_window / dpg.child_window calls are resizable.
    """
    import dearpygui.dearpygui as _dpg
    _dpg.add_child_window = add_child_window
    _dpg.child_window     = child_window
