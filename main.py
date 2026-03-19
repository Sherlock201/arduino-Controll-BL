# main.py
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.clock import Clock

import threading
import os

# Flask
from flask import Flask, send_from_directory, render_template_string

try:
    _  # если не определено — определим как identity
except NameError:
    _ = lambda s: s

# pyjnius (Android)
try:
    from jnius import autoclass, PythonJavaClass, java_method
    AndroidAvailable = True
except Exception as e:
    AndroidAvailable = False
    print("pyjnius not available:", e)

# --- Flask app ---
www_dir = os.path.join(os.getcwd(), 'www')
app = Flask(__name__, static_folder=www_dir, template_folder=www_dir)

@app.route('/')
def index():
    index_path = os.path.join(www_dir, 'index.html')
    if os.path.exists(index_path):
        return render_template_string(open(index_path, 'r', encoding='utf-8').read())
    return "<h1>Flask running</h1><p>Put index.html into /www folder.</p>"

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(www_dir, filename)

def run_flask():
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)

# --- WebView handling (Android) ---
webview_ref = {'view': None, 'listener': None}

if AndroidAvailable:
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    WebView = autoclass('android.webkit.WebView')
    WebViewClient = autoclass('android.webkit.WebViewClient')
    ViewGroupLayoutParams = autoclass('android.view.ViewGroup$LayoutParams')
    View = autoclass('android.view.View')
    ActivityInfo = autoclass('android.content.pm.ActivityInfo')

    # --- Fullscreen Runnable ---
    class FullscreenRunnable(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']

        @java_method('()V')
        def run(self):
            try:
                activity = PythonActivity.mActivity
                if not activity: return
                window = activity.getWindow()
                BuildVersion = autoclass('android.os.Build$VERSION')

                # Убираем системные отступы
                try:
                    WindowCompat = autoclass('androidx.core.view.WindowCompat')
                    WindowCompat.setDecorFitsSystemWindows(window, False)
                except:
                    pass

                # WindowInsetsController для API 30+
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

                # Флаги окна
                WindowManager = autoclass('android.view.WindowManager$LayoutParams')
                window.addFlags(WindowManager.FLAG_FULLSCREEN)
                window.addFlags(WindowManager.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)

                # Cutout mode для вырезов
                if BuildVersion.SDK_INT >= 28:
                    params = window.getAttributes()
                    params.layoutInDisplayCutoutMode = 1
                    window.setAttributes(params)

                # Immersive Mode
                decorView = window.getDecorView()
                uiOptions = (
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY |
                    View.SYSTEM_UI_FLAG_LAYOUT_STABLE |
                    View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION |
                    View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN |
                    View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
                    View.SYSTEM_UI_FLAG_FULLSCREEN
                )
                decorView.setSystemUiVisibility(uiOptions)

                # Listener для восстановления флагов при сбросе
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
                print("Fullscreen error:", e)

    # --- WebView Runnables ---
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

            # Загружаем index.html
            try:
                www_path = os.path.join(os.getcwd(), 'www', 'index.html')
                if os.path.exists(www_path):
                    with open(www_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                else:
                    html_content = "<html><body><h1>index.html not found</h1></body></html>"
            except Exception as e:
                html_content = f"<html><body><h1>Error reading file: {e}</h1></body></html>"

            wv.loadDataWithBaseURL('http://localhost:5000/', html_content, 'text/html', 'UTF-8', None)
            wv.setWebViewClient(WebViewClient())

            params = ViewGroupLayoutParams(ViewGroupLayoutParams.MATCH_PARENT, ViewGroupLayoutParams.MATCH_PARENT)
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

# --- Kivy App ---
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
        self.set_fullscreen()
        activity = PythonActivity.mActivity
        if activity:
            activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)
        self.open_webview()

    # --- Fullscreen / WebView Functions ---
    def set_fullscreen(self, *args):
        if AndroidAvailable and PythonActivity.mActivity:
            if self._fs_runnable is None:
                self._fs_runnable = FullscreenRunnable()
            PythonActivity.mActivity.runOnUiThread(self._fs_runnable)

    def fix_webview_fullscreen(self):
        if not AndroidAvailable:
            return

        def apply_flags():
            try:
                wv = webview_ref.get('view')
                if wv:
                    uiOptions = (
                        View.SYSTEM_UI_FLAG_LAYOUT_STABLE |
                        View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION |
                        View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN |
                        View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
                        View.SYSTEM_UI_FLAG_FULLSCREEN |
                        View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    )
                    wv.setSystemUiVisibility(uiOptions)
            except Exception as e:
                print("WebView fullscreen fix error:", e)

        class RunnableFix(PythonJavaClass):
            __javainterfaces__ = ['java/lang/Runnable']

            @java_method('()V')
            def run(self):
                apply_flags()

        PythonActivity.mActivity.runOnUiThread(RunnableFix())

    def on_resume(self):
        if not AndroidAvailable:
            return
        self.set_fullscreen()
        for t in [0.3, 1.0, 2.5]:
            Clock.schedule_once(lambda dt: self.set_fullscreen(), t)
        self.fix_webview_fullscreen()
        Clock.schedule_once(lambda dt: self.fix_webview_fullscreen(), 0.5)
        try:
            activity = PythonActivity.mActivity
            if activity:
                activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)
        except Exception as e:
            print("Orientation error:", e)
        Clock.schedule_interval(lambda dt: self.set_fullscreen(), 0.5)

    # --- Flask / WebView control ---
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

    def close_webview(self):
        if not AndroidAvailable:
            return
        PythonActivity.mActivity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)
        PythonActivity.mActivity.runOnUiThread(_RemoveWebViewRunnable())

    def on_stop(self):
        if AndroidAvailable:
            PythonActivity.mActivity.runOnUiThread(_RemoveWebViewRunnable())

if __name__ == '__main__':
    TestApp().run()
