# main.py
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.widget import Widget

import threading
import os
import logging

from flask import Flask, send_from_directory, render_template_string

try:
    _  # if not defined, define identity
except NameError:
    _ = lambda s: s

try:
    from jnius import autoclass, PythonJavaClass, java_method
    AndroidAvailable = True
except Exception as e:
    AndroidAvailable = False
    print("pyjnius not available:", e)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- Flask app ---
www_dir = os.path.join(os.getcwd(), "www")
app = Flask(__name__, static_folder=www_dir, template_folder=www_dir)

@app.route("/")
def index():
    index_path = os.path.join(www_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return render_template_string(f.read())
    return "<h1>Flask running</h1><p>Put index.html into /www folder.</p>"

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(www_dir, filename)

def run_flask():
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)

# --- Android / WebView ---
webview_ref = {
    "view": None,
    "listener": None,
    "back_handler": None,
}

if AndroidAvailable:
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    WebView = autoclass("android.webkit.WebView")
    WebViewClient = autoclass("android.webkit.WebViewClient")
    ViewGroupLayoutParams = autoclass("android.view.ViewGroup$LayoutParams")
    View = autoclass("android.view.View")
    ActivityInfo = autoclass("android.content.pm.ActivityInfo")
    BuildVersion = autoclass("android.os.Build$VERSION")
    Build = autoclass("android.os.Build")
    Color = autoclass("android.graphics.Color")

    class UiListener(PythonJavaClass):
        __javainterfaces__ = ["android/view/View$OnSystemUiVisibilityChangeListener"]
        ui_options = 0

        @java_method("(I)V")
        def onSystemUiVisibilityChange(self, vis):
            try:
                act = PythonActivity.mActivity
                if not act:
                    return
                win = act.getWindow()
                if not win:
                    return
                dv = win.getDecorView()
                if dv:
                    dv.setSystemUiVisibility(UiListener.ui_options)
            except Exception as e:
                print("UiListener error:", e)

    class BackHandler(PythonJavaClass):
        __javainterfaces__ = ["android/view/View$OnKeyListener"]

        @java_method("(Landroid/view/View;ILandroid/view/KeyEvent;)Z")
        def onKey(self, v, keyCode, event):
            try:
                # 4 = KEYCODE_BACK, 0 = ACTION_DOWN
                if keyCode == 4 and event.getAction() == 0:
                    wv = webview_ref.get("view")
                    if wv and wv.canGoBack():
                        wv.goBack()
                        return True
            except Exception as e:
                print("BackHandler error:", e)
            return False

    class FullscreenRunnable(PythonJavaClass):
        __javainterfaces__ = ["java/lang/Runnable"]

        @java_method("()V")
        def run(self):
            try:
                activity = PythonActivity.mActivity
                if not activity:
                    return

                window = activity.getWindow()
                if not window:
                    return

                decorView = window.getDecorView()
                if not decorView:
                    return

                # Edge-to-edge
                try:
                    WindowCompat = autoclass("androidx.core.view.WindowCompat")
                    WindowCompat.setDecorFitsSystemWindows(window, False)
                except Exception:
                    pass

                WindowManager = autoclass("android.view.WindowManager$LayoutParams")

                # Make bars transparent
                try:
                    window.addFlags(WindowManager.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)
                    window.setStatusBarColor(Color.TRANSPARENT)
                    window.setNavigationBarColor(Color.TRANSPARENT)
                except Exception as e:
                    print("Bar color error:", e)

                # Keep content full screen
                window.addFlags(WindowManager.FLAG_FULLSCREEN)

                # Immersive flags for older API / compatibility
                uiOptions = (
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_FULLSCREEN
                )
                UiListener.ui_options = uiOptions
                decorView.setSystemUiVisibility(uiOptions)

                # API 30+ controller
                if BuildVersion.SDK_INT >= 30:
                    try:
                        WindowInsetsController = autoclass("android.view.WindowInsetsController")
                        WindowInsets = autoclass("android.view.WindowInsets")
                        controller = window.getInsetsController()
                        if controller:
                            controller.hide(WindowInsets.Type.systemBars())
                            controller.setSystemBarsBehavior(
                                WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                            )
                    except Exception as e:
                        print("Insets fullscreen error:", e)

                # Cutout / notch handling
                if BuildVersion.SDK_INT >= 28:
                    try:
                        params = window.getAttributes()
                        params.layoutInDisplayCutoutMode = 1  # SHORT_EDGES
                        window.setAttributes(params)
                    except Exception as e:
                        print("Cutout mode error:", e)

                # Reapply on UI visibility changes
                old_listener = webview_ref.get("listener")
                if old_listener:
                    webview_ref["listener"] = None

                listener = UiListener()
                decorView.setOnSystemUiVisibilityChangeListener(listener)
                webview_ref["listener"] = listener

                decorView.setFitsSystemWindows(False)

            except Exception as e:
                print(f"Fullscreen error: {e}")

    class _AddWebViewRunnable(PythonJavaClass):
        __javainterfaces__ = ["java/lang/Runnable"]

        def __init__(self, url):
            super().__init__()
            self.url = url
            self.html_content = self._load_html_content()

        def _load_html_content(self):
            try:
                www_path = os.path.join(os.getcwd(), "www", "index.html")
                if os.path.exists(www_path):
                    with open(www_path, "r", encoding="utf-8") as f:
                        return f.read()
                return "<html><body><h1>index.html not found in /www</h1></body></html>"
            except Exception as e:
                return f"<html><body><h1>Error reading file: {str(e)}</h1></body></html>"

        @java_method("()V")
        def run(self):
            try:
                activity = PythonActivity.mActivity
                if not activity:
                    return

                wv = WebView(activity)
                settings = wv.getSettings()

                settings.setJavaScriptEnabled(True)
                settings.setDomStorageEnabled(True)
                settings.setAllowFileAccess(True)
                settings.setAllowContentAccess(True)
                settings.setMixedContentMode(0)
                settings.setUseWideViewPort(True)
                settings.setLoadWithOverviewMode(True)
                settings.setSupportZoom(False)

                wv.setInitialScale(0)
                wv.setVerticalScrollBarEnabled(False)
                wv.setHorizontalScrollBarEnabled(False)
                wv.setFocusable(True)
                wv.setFocusableInTouchMode(True)
                wv.clearFocus()

                # Apply same fullscreen flags to WebView itself
                uiOptions = (
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_FULLSCREEN
                )
                wv.setSystemUiVisibility(uiOptions)

                wv.setWebViewClient(WebViewClient())

                back_handler = BackHandler()
                wv.setOnKeyListener(back_handler)
                webview_ref["back_handler"] = back_handler

                wv.loadDataWithBaseURL(
                    "http://localhost:5000/",
                    self.html_content,
                    "text/html",
                    "UTF-8",
                    None
                )

                params = ViewGroupLayoutParams(
                    ViewGroupLayoutParams.MATCH_PARENT,
                    ViewGroupLayoutParams.MATCH_PARENT
                )
                activity.addContentView(wv, params)
                webview_ref["view"] = wv

            except Exception as e:
                print(f"Error adding WebView: {e}")

    class _RemoveWebViewRunnable(PythonJavaClass):
        __javainterfaces__ = ["java/lang/Runnable"]

        @java_method("()V")
        def run(self):
            try:
                activity = PythonActivity.mActivity
                wv = webview_ref.get("view")
                if wv:
                    parent = wv.getParent()
                    if parent:
                        parent.removeView(wv)
                webview_ref["view"] = None
                webview_ref["back_handler"] = None
                webview_ref["listener"] = None
            except Exception as e:
                print(f"Error removing WebView: {e}")

class TestApp(App):
    def build(self):
        self.flask_thread = None
        self._fs_runnable = None
        return Widget()

    def start_flask(self):
        if not self.flask_thread or not self.flask_thread.is_alive():
            t = threading.Thread(target=run_flask, daemon=True)
            t.start()
            self.flask_thread = t

    def set_fullscreen(self, *args):
        if AndroidAvailable and PythonActivity.mActivity:
            if self._fs_runnable is None:
                self._fs_runnable = FullscreenRunnable()
            PythonActivity.mActivity.runOnUiThread(self._fs_runnable)

    def fix_webview_fullscreen(self, *args):
        if not AndroidAvailable or not PythonActivity.mActivity:
            return

        def apply_flags():
            try:
                wv = webview_ref.get("view")
                if not wv:
                    return

                uiOptions = (
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_FULLSCREEN
                )
                wv.setSystemUiVisibility(uiOptions)
            except Exception as e:
                print("WebView fullscreen fix error:", e)

        class RunnableFix(PythonJavaClass):
            __javainterfaces__ = ["java/lang/Runnable"]

            @java_method("()V")
            def run(self):
                apply_flags()

        PythonActivity.mActivity.runOnUiThread(RunnableFix())

    def open_webview(self):
        if not AndroidAvailable:
            import webbrowser
            webbrowser.open("http://127.0.0.1:5000")
            return

        runnable = _AddWebViewRunnable("http://localhost:5000/")
        PythonActivity.mActivity.runOnUiThread(runnable)

    def initial_android_setup(self, dt):
        if not AndroidAvailable:
            return
        try:
            self.set_fullscreen()

            activity = PythonActivity.mActivity
            if activity:
                activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)

            self.open_webview()
        except Exception as e:
            print(f"Late Init Error: {e}")

    def on_start(self):
        self.start_flask()
        Clock.schedule_once(self.initial_android_setup, 1.5)

    def on_resume(self):
        if not AndroidAvailable:
            return

        # Re-apply at resume; docs recommend onResume / focus changes
        self.set_fullscreen()
        Clock.schedule_once(lambda dt: self.set_fullscreen(), 0.1)
        Clock.schedule_once(lambda dt: self.set_fullscreen(), 0.5)
        Clock.schedule_once(lambda dt: self.set_fullscreen(), 1.0)

        self.fix_webview_fullscreen()
        Clock.schedule_once(lambda dt: self.fix_webview_fullscreen(), 0.1)
        Clock.schedule_once(lambda dt: self.fix_webview_fullscreen(), 0.5)

        try:
            if PythonActivity.mActivity:
                PythonActivity.mActivity.setRequestedOrientation(
                    ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
                )
        except Exception as e:
            print(f"Orientation error: {e}")

    def on_pause(self):
        return True

    def on_stop(self):
        if AndroidAvailable and PythonActivity.mActivity:
            webview_ref["listener"] = None
            webview_ref["back_handler"] = None
            PythonActivity.mActivity.runOnUiThread(_RemoveWebViewRunnable())

if __name__ == "__main__":
    TestApp().run()
