# main.py
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.clock import Clock
import threading
import os

from flask import Flask, send_from_directory, render_template_string

try:
    _ = lambda s: s
except NameError:
    pass

try:
    from jnius import autoclass, PythonJavaClass, java_method
    AndroidAvailable = True
except Exception as e:
    AndroidAvailable = False
    print("pyjnius not available:", e)

# --- Flask app ---
www_dir = os.path.join(os.getcwd(), 'www')
flask_app = Flask(__name__, static_folder=www_dir, template_folder=www_dir)

@flask_app.route('/')
def index():
    index_path = os.path.join(www_dir, 'index.html')
    if os.path.exists(index_path):
        return render_template_string(open(index_path, 'r', encoding='utf-8').read())
    return "<h1>Flask running</h1><p>Put index.html into /www folder.</p>"

@flask_app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(www_dir, filename)

def run_flask():
    flask_app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)

# --- WebView and Fullscreen ---
# Расширяем webview_ref для хранения последнего decorView и слушателя
webview_ref = {'view': None, 'listener': None, 'decor_view': None}

if AndroidAvailable:
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    WebView = autoclass('android.webkit.WebView')
    WebViewClient = autoclass('android.webkit.WebViewClient')
    ViewGroupLayoutParams = autoclass('android.view.ViewGroup$LayoutParams')
    View = autoclass('android.view.View')
    ActivityInfo = autoclass('android.content.pm.ActivityInfo')
    BuildVersion = autoclass('android.os.Build$VERSION')
    Build = autoclass('android.os.Build')

    class UiListener(PythonJavaClass):
        __javainterfaces__ = ['android/view/View$OnSystemUiVisibilityChangeListener']
        def __init__(self, uiOptions):
            super().__init__()
            self.uiOptions = uiOptions

        @java_method('(I)V')
        def onSystemUiVisibilityChange(self, vis):
            try:
                act = PythonActivity.mActivity
                if not act:
                    return
                win = act.getWindow()
                if not win:
                    return
                decorView = win.getDecorView()
                if not decorView:
                    return
                decorView.setSystemUiVisibility(self.uiOptions)
            except Exception as e:
                print("UiListener error:", e)

    class FullscreenRunnable(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']
        @java_method('()V')
        def run(self):
            try:
                activity = PythonActivity.mActivity
                if not activity:
                    return
                window = activity.getWindow()
                WindowManager = autoclass('android.view.WindowManager$LayoutParams')

                window.addFlags(WindowManager.FLAG_FULLSCREEN)
                window.addFlags(WindowManager.FLAG_LAYOUT_IN_SCREEN)
                window.addFlags(WindowManager.FLAG_LAYOUT_NO_LIMITS)
                window.addFlags(WindowManager.FLAG_TRANSLUCENT_STATUS)
                window.addFlags(WindowManager.FLAG_TRANSLUCENT_NAVIGATION)
                window.addFlags(WindowManager.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)

                try:
                    window.setDecorFitsSystemWindows(False)
                except:
                    pass

                if BuildVersion.SDK_INT >= 28:
                    params = window.getAttributes()
                    params.layoutInDisplayCutoutMode = 1
                    window.setAttributes(params)

                controller = None
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
                        print("Insets error:", e)

                decorView = window.getDecorView()
                uiOptions = (
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LOW_PROFILE
                )
                decorView.setSystemUiVisibility(uiOptions)

                # Удаляем старый слушатель с предыдущего decorView
                old_decor = webview_ref.get('decor_view')
                if old_decor:
                    try:
                        old_decor.setOnSystemUiVisibilityChangeListener(None)
                    except:
                        pass
                    webview_ref['decor_view'] = None

                # Создаём и устанавливаем новый слушатель
                new_listener = UiListener(uiOptions)
                decorView.setOnSystemUiVisibilityChangeListener(new_listener)
                webview_ref['listener'] = new_listener
                webview_ref['decor_view'] = decorView
                decorView.setFitsSystemWindows(False)

                if controller:
                    controller.hide(
                        WindowInsets.Type.statusBars() |
                        WindowInsets.Type.navigationBars()
                    )
                    window.setFlags(
                        WindowManager.FLAG_LAYOUT_NO_LIMITS,
                        WindowManager.FLAG_LAYOUT_NO_LIMITS
                    )
            except Exception as e:
                print(f"Fullscreen error: {e}")

    class _AddWebViewRunnable(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']
        def __init__(self, url):
            super().__init__()
            self.url = url
            self.html_content = self._load_html_content()

        def _load_html_content(self):
            try:
                www_path = os.path.join(os.getcwd(), 'www', 'index.html')
                if os.path.exists(www_path):
                    with open(www_path, 'r', encoding='utf-8') as f:
                        return f.read()
                return "<html><body><h1>index.html not found</h1></body></html>"
            except Exception as e:
                return f"<html><body><h1>Error: {e}</h1></body></html>"

        @java_method('()V')
        def run(self):
            try:
                activity = PythonActivity.mActivity
                if not activity:
                    return

                # Удаляем старый WebView, если есть
                old_wv = webview_ref.get('view')
                if old_wv:
                    parent = old_wv.getParent()
                    if parent:
                        parent.removeView(old_wv)
                    webview_ref['view'] = None

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
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LOW_PROFILE
                )
                wv.clearFocus()
                wv.setWebViewClient(WebViewClient())
                wv.loadDataWithBaseURL('http://localhost:5000/',
                                        self.html_content,
                                        'text/html', 'UTF-8', None)

                params = ViewGroupLayoutParams(
                    ViewGroupLayoutParams.MATCH_PARENT,
                    ViewGroupLayoutParams.MATCH_PARENT
                )
                activity.addContentView(wv, params)
                webview_ref['view'] = wv
            except Exception as e:
                print(f"Error adding WebView: {e}")

    class _RemoveWebViewRunnable(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']
        @java_method('()V')
        def run(self):
            try:
                activity = PythonActivity.mActivity
                if not activity:
                    return
                wv = webview_ref.get('view')
                if wv:
                    parent = wv.getParent()
                    if parent:
                        parent.removeView(wv)
                    webview_ref['view'] = None
            except Exception as e:
                print(f"Error removing WebView: {e}")

# --- Kivy app ---
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
            activity = PythonActivity.mActivity
            if activity:
                activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)
            self.set_fullscreen()
            self.open_webview()
        except Exception as e:
            print(f"Init Error: {e}")

    def set_fullscreen(self, *args):
        if AndroidAvailable and PythonActivity.mActivity:
            if self._fs_runnable is None:
                self._fs_runnable = FullscreenRunnable()
            PythonActivity.mActivity.runOnUiThread(self._fs_runnable)

    def remove_ui_listener(self):
        """Снимает слушатель системных UI с сохранённого decorView."""
        if AndroidAvailable:
            old_decor = webview_ref.get('decor_view')
            if old_decor:
                try:
                    old_decor.setOnSystemUiVisibilityChangeListener(None)
                except Exception as e:
                    print(f"Error removing listener: {e}")
            webview_ref['decor_view'] = None
            webview_ref['listener'] = None

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

    def fix_webview_fullscreen(self):
        if not AndroidAvailable:
            return

        def apply_flags():
            try:
                wv = webview_ref.get('view')
                if wv:
                    wv.setSystemUiVisibility(
                        View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LOW_PROFILE
                    )
                    if BuildVersion.SDK_INT >= 30:
                        try:
                            WindowInsetsController = autoclass('android.view.WindowInsetsController')
                            WindowInsets = autoclass('android.view.WindowInsets')
                            window = PythonActivity.mActivity.getWindow()
                            controller = window.getInsetsController()
                            if controller:
                                controller.hide(
                                    WindowInsets.Type.statusBars() |
                                    WindowInsets.Type.navigationBars()
                                )
                        except:
                            pass
            except Exception as e:
                print("WebView fix error:", e)

        class RunnableFix(PythonJavaClass):
            __javainterfaces__ = ['java/lang/Runnable']
            @java_method('()V')
            def run(self):
                apply_flags()

        PythonActivity.mActivity.runOnUiThread(RunnableFix())

    def on_resume(self):
        if not AndroidAvailable:
            return
        print("App resumed - reapplying fullscreen")
        # Сначала удаляем старый слушатель, чтобы он не вызывался при восстановлении
        self.remove_ui_listener()
        Clock.unschedule(self.set_fullscreen)
        intervals = [0.1, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 2.5, 3.0]
        for interval in intervals:
            Clock.schedule_once(lambda dt: self.set_fullscreen(), interval)

        self.fix_webview_fullscreen()
        Clock.schedule_once(lambda dt: self.fix_webview_fullscreen(), 0.5)
        Clock.schedule_once(lambda dt: self.fix_webview_fullscreen(), 1.0)

        if PythonActivity.mActivity:
            PythonActivity.mActivity.setRequestedOrientation(
                ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
            )

    def on_pause(self):
        if AndroidAvailable:
            # Снимаем слушатель, чтобы он не вызывался после паузы
            self.remove_ui_listener()
            Clock.unschedule(self.set_fullscreen)
        return True

    def on_stop(self):
        if AndroidAvailable:
            self.remove_ui_listener()
            PythonActivity.mActivity.runOnUiThread(_RemoveWebViewRunnable())

if __name__ == '__main__':
    TestApp().run()
