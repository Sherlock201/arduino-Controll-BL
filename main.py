from kivy.app import App
from kivy.clock import Clock
from kivy.uix.widget import Widget

import threading
import os

# Flask
from flask import Flask, send_from_directory, render_template_string

# pyjnius
try:
    from jnius import autoclass, PythonJavaClass, java_method
    AndroidAvailable = True
except Exception as e:
    AndroidAvailable = False
    print("pyjnius not available:", e)

# -------------------- Flask --------------------

www_dir = os.path.join(os.getcwd(), 'www')
app = Flask(__name__, static_folder=www_dir, template_folder=www_dir)

@app.route('/')
def index():
    index_path = os.path.join(www_dir, 'index.html')
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            return render_template_string(f.read())
    return "<h1>No index.html</h1>"

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(www_dir, filename)

def run_flask():
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)

# -------------------- Android --------------------

webview_ref = {'view': None}

if AndroidAvailable:
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    WebView = autoclass('android.webkit.WebView')
    WebViewClient = autoclass('android.webkit.WebViewClient')
    LayoutParams = autoclass('android.view.ViewGroup$LayoutParams')
    View = autoclass('android.view.View')
    ActivityInfo = autoclass('android.content.pm.ActivityInfo')

    class FullscreenRunnable(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']

        @java_method('()V')
        def run(self):
            try:
                activity = PythonActivity.mActivity
                if not activity:
                    return

                window = activity.getWindow()
                if not window:
                    return

                decor = window.getDecorView()

                ui = (
                    View.SYSTEM_UI_FLAG_LAYOUT_STABLE |
                    View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION |
                    View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN |
                    View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
                    View.SYSTEM_UI_FLAG_FULLSCREEN |
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                )

                decor.setSystemUiVisibility(ui)

            except Exception as e:
                print("Fullscreen error:", e)

    class AddWebView(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']

        def __init__(self):
            super().__init__()

        @java_method('()V')
        def run(self):
            try:
                activity = PythonActivity.mActivity
                if not activity:
                    print("No activity")
                    return

                wv = WebView(activity)

                settings = wv.getSettings()
                settings.setJavaScriptEnabled(True)
                settings.setDomStorageEnabled(True)
                settings.setAllowFileAccess(True)
                settings.setAllowContentAccess(True)

                settings.setUseWideViewPort(True)
                settings.setLoadWithOverviewMode(True)
                settings.setSupportZoom(False)

                wv.setVerticalScrollBarEnabled(False)
                wv.setHorizontalScrollBarEnabled(False)

                # Загружаем HTML напрямую
                try:
                    path = os.path.join(os.getcwd(), 'www', 'index.html')
                    with open(path, 'r', encoding='utf-8') as f:
                        html = f.read()
                except:
                    html = "<h1>index.html not found</h1>"

                wv.loadDataWithBaseURL(
                    'http://localhost:5000/',
                    html,
                    'text/html',
                    'UTF-8',
                    None
                )

                wv.setWebViewClient(WebViewClient())

                params = LayoutParams(
                    LayoutParams.MATCH_PARENT,
                    LayoutParams.MATCH_PARENT
                )

                activity.addContentView(wv, params)

                webview_ref['view'] = wv

            except Exception as e:
                print("WebView error:", e)

# -------------------- App --------------------

class TestApp(App):

    def build(self):
        self.flask_thread = None
        self.fs = None
        return Widget()

    def on_start(self):
        self.start_flask()

        # Ждём пока всё поднимется
        Clock.schedule_once(self.setup_android, 2.5)

    def setup_android(self, dt):
        if not AndroidAvailable:
            return

        try:
            self.set_fullscreen()

            activity = PythonActivity.mActivity
            if activity:
                activity.setRequestedOrientation(
                    ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
                )

            # КРИТИЧНО: ждём после смены ориентации
            Clock.schedule_once(self.open_webview, 1.0)

        except Exception as e:
            print("Setup error:", e)

    def set_fullscreen(self, *args):
        if AndroidAvailable and PythonActivity.mActivity:
            if not self.fs:
                self.fs = FullscreenRunnable()
            PythonActivity.mActivity.runOnUiThread(self.fs)

    def start_flask(self):
        if not self.flask_thread:
            t = threading.Thread(target=run_flask, daemon=True)
            t.start()
            self.flask_thread = t

    def open_webview(self, dt):
        if not AndroidAvailable:
            return

        PythonActivity.mActivity.runOnUiThread(AddWebView())

# --------------------

if __name__ == '__main__':
    TestApp().run()
