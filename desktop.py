import threading
import webview
from app import app

main_window = None


class Api:
    def choose_save_path(self, default_filename):
        global main_window

        if main_window is None:
            return None

        result = main_window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=default_filename
        )

        if not result:
            return None

        if isinstance(result, (list, tuple)):
            return result[0]

        return result


def run_flask():
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False
    )


if __name__ == "__main__":
    api = Api()

    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True
    )

    flask_thread.start()

    main_window = webview.create_window(
        "YT Downloader",
        "http://127.0.0.1:5000",
        width=1200,
        height=850,
        js_api=api
    )

    webview.start()