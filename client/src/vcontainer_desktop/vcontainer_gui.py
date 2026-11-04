import ctypes
import webview

from vcontainer_cli import API_HOST, API_PORT, WSL_DISTRO, ensure_backend

desktop_window = None
window_maximized = False

WINDOW_CONFIG = {
    "title": "Vcontainer",
    "url": f"http://{API_HOST}:{API_PORT}/?desktop=1",
    "width": 1280,
    "height": 800,
    "min_size": (900, 600),
    "frameless": True,
    "easy_drag": False,
    "shadow": True,
    "resizable": True,
    "background_color": "#1c2733",
}

GUI_START = {
    "gui": "edgechromium",
    "debug": False,
}


class WindowControls:
    def minimize(self):
        desktop_window.minimize()

    def resize_window(self, x, y, width, height):
        try:
            x = int(x)
            y = int(y)
            width = max(900, int(width))
            height = max(600, int(height))
        except (TypeError, ValueError):
            return False

        desktop_window.move(x, y)
        desktop_window.resize(width, height)
        return True

    def toggle_maximize(self):
        global window_maximized

        if window_maximized:
            desktop_window.restore()
        else:
            desktop_window.maximize()

        window_maximized = not window_maximized

        return window_maximized

    def close(self):
        desktop_window.destroy()


def show_error(message):
    ctypes.windll.user32.MessageBoxW(
        None,
        message,
        "Vcontainer",
        0x10,
    )


def main():
    global desktop_window

    try:
        ensure_backend(WSL_DISTRO)

        desktop_window = webview.create_window(
            **WINDOW_CONFIG,
            js_api=WindowControls(),
        )
        webview.start(**GUI_START)

    except Exception as error:
        show_error(str(error))


if __name__ == "__main__":
    main()
