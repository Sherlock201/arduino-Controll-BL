# main.py
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock
from kivy.uix.widget import Widget

import threading
import os

# Flask
from flask import Flask, send_from_directory, render_template_string

try:
    _
except NameError:
    _ = lambda s: s

# pyjnius (Android)
try:
    from jnius import autoclass, PythonJavaClass, java_method
    AndroidAvailable = True
except Exception as e:
    AndroidAvailable = False
    print("pyjnius not available:", e)

# --- Flask ---
www_dir = os.path.join(os.getcwd(), 'www')
app = Flask(__name__, static_folder=www_dir, template_folder=www_dir)

@app.route('/')
def index():
    index_path = os.path.join(www_dir, 'index.html')
    if os.path.exists(index_path):
        return render_template_string(open(index_path, 'r', encoding='utf-8').read())
    return "<h1>Flask running</h1>"

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(www_dir, filename)

def run_flask():
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)

# --- Android ---
webview_ref = {'view': None}

if AndroidAvailable:
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    WebView = autoclass('android.webkit.WebView')
    WebViewClient = autoclass('android.webkit.WebViewClient')
    ViewGroupLayoutParams = autoclass('android.view.ViewGroup$LayoutParams')
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

                BuildVersion = autoclass('android.os.Build$VERSION')
                controller = None

                try:
                    WindowCompat = autoclass('androidx.core.view.WindowCompat')
                    WindowCompat.setDecorFitsSystemWindows(window, False)
                except:
                    pass

                if BuildVersion.SDK_INT >= 30:
                    try:
                        WindowInsetsController = autoclass('android.view.WindowInsetsController')
                        WindowInsets = autoclass('android.view.WindowInsets')
                        controller = window.getInsetsController()
                        if controller:
                            controller.hide(
                                WindowInsets.Type.statusBars() |
                                WindowInsets.Type.navigationBars()
                            )
                            controller.setSystemBarsBehavior(
                                WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                            )
                    except Exception as e:
                        print("Insets fullscreen error:", e)

                WindowManager = autoclass('android.view.WindowManager$LayoutParams')
                window.addFlags(WindowManager.FLAG_FULLSCREEN)
                window.addFlags(WindowManager.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)

                if BuildVersion.SDK_INT >= 28:
                    params = window.getAttributes()
                    params.layoutInDisplayCutoutMode = 1
                    window.setAttributes(params)

                decorView = window.getDecorView()
                uiOptions = (
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_FULLSCREEN
                )
                decorView.setSystemUiVisibility(uiOptions)

                decorView_local = decorView
                uiOptions_local = uiOptions

                class UiListener(PythonJavaClass):
                    __javainterfaces__ = ['android/view/View$OnSystemUiVisibilityChangeListener']

                    @java_method('(I)V')
                    def onSystemUiVisibilityChange(self, vis):
                        try:
                            decorView_local.setSystemUiVisibility(uiOptions_local)
                        except Exception as e:
                            print("UiListener error:", e)

                listener = UiListener()
                decorView.setOnSystemUiVisibilityChangeListener(listener)
                webview_ref['listener'] = listener
                decorView.setFitsSystemWindows(False)

            except Exception as e:
                print(f"Fullscreen error: {e}")

    class _AddWebViewRunnable(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']

        def __init__(self, url):
            super().__init__()
            self.url = url

        @java_method('()V')
        def run(self):
            activity = PythonActivity.mActivity
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

            wv.setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE |
                View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION |
                View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN |
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
                View.SYSTEM_UI_FLAG_FULLSCREEN |
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            )

            wv.clearFocus()

            try:
                www_path = os.path.join(os.getcwd(), 'www', 'index.html')
                if os.path.exists(www_path):
                    with open(www_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                else:
                    html_content = "<html><body>index.html not found</body></html>"
            except Exception as e:
                html_content = f"<html><body>Error: {str(e)}</body></html>"

            wv.loadDataWithBaseURL(
                'http://localhost:5000/',
                html_content,
                'text/html',
                'UTF-8',
                None
            )

            wv.setWebViewClient(WebViewClient())
            params = ViewGroupLayoutParams(
                ViewGroupLayoutParams.MATCH_PARENT,
                ViewGroupLayoutParams.MATCH_PARENT
            )
            activity.addContentView(wv, params)
            webview_ref['view'] = wv

    class _RemoveWebViewRunnable(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']

        @java_method('()V')
        def run(self):
            activity = PythonActivity.mActivity
            wv = webview_ref.get('view')
            if wv:
                parent = wv.getParent()
                if parent:
                    parent.removeView(wv)
                webview_ref['view'] = None

# --- App ---
class TestApp(App):
    def build(self):
        self.flask_thread = None
        self._fs_runnable = None
        return Widget()

    def on_start(self):
        self.start_flask()
        Clock.schedule_once(self.initial_android_setup, 1.5)

    def initial_android_setup(self, dt):
        if not AndroidAvailable:
            return
        try:
            self.set_fullscreen()

            activity = PythonActivity.mActivity
            if activity:
                activity.setRequestedOrientation(
                    ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
                )

            self.open_webview()
        except Exception as e:
            print(f"Init error: {e}")

    def set_fullscreen(self, *args):
        if AndroidAvailable and PythonActivity.mActivity:
            if self._fs_runnable is None:
                self._fs_runnable = FullscreenRunnable()
            PythonActivity.mActivity.runOnUiThread(self._fs_runnable)

    def start_flask(self):
        if not self.flask_thread or not self.flask_thread.is_alive():
            t = threading.Thread(target=run_flask, daemon=True)
            t.start()
            self.flask_thread = t

    def open_webview(self):
        if not AndroidAvailable:
            import webbrowser
            webbrowser.open('http://127.0.0.1:5000')
            return

        runnable = _AddWebViewRunnable('http://localhost:5000/')
        PythonActivity.mActivity.runOnUiThread(runnable)

    def on_resume(self):
        if AndroidAvailable:
            self.set_fullscreen()

            Clock.schedule_once(lambda dt: self.set_fullscreen(), 0.3)
            Clock.schedule_once(lambda dt: self.set_fullscreen(), 1.0)
            Clock.schedule_once(lambda dt: self.set_fullscreen(), 2.0)

            if PythonActivity.mActivity:
                PythonActivity.mActivity.setRequestedOrientation(
                    ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
                )

if __name__ == '__main__':
    TestApp().run()
