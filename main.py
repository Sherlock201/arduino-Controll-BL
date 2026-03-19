# main.py (полностью исправленный)
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.widget import Widget
import threading
import os
import logging

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

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- Flask ---
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
webview_ref = {'view': None, 'ui_listener': None, 'back_handler': None}

if AndroidAvailable:
    # Импорты Java
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    WebView = autoclass('android.webkit.WebView')
    WebViewClient = autoclass('android.webkit.WebViewClient')
    ViewGroupLayoutParams = autoclass('android.view.ViewGroup$LayoutParams')
    View = autoclass('android.view.View')
    ActivityInfo = autoclass('android.content.pm.ActivityInfo')
    BuildVersion = autoclass('android.os.Build$VERSION')
    Build = autoclass('android.os.Build')

    # --- Listener для системных UI (без хранения View) ---
    class XiaomiUiListener(PythonJavaClass):
        __javainterfaces__ = ['android/view/View$OnSystemUiVisibilityChangeListener']
        
        def __init__(self, uiOptions):
            super().__init__()
            self.uiOptions = uiOptions

        @java_method('(I)V')
        def onSystemUiVisibilityChange(self, visibility):
            try:
                activity = PythonActivity.mActivity
                if not activity:
                    return
                decorView = activity.getWindow().getDecorView()
                decorView.setSystemUiVisibility(self.uiOptions)
            except Exception as e:
                print(f"XiaomiUiListener error: {e}")

    # --- Fullscreen Runnable ---
    class FullscreenRunnable(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']
        
        @java_method('()V')
        def run(self):
            try:
                activity = PythonActivity.mActivity
                if not activity:
                    return
                window = activity.getWindow()
                decorView = window.getDecorView()

                WindowManager = autoclass('android.view.WindowManager$LayoutParams')
                window.addFlags(WindowManager.FLAG_FULLSCREEN)
                window.addFlags(WindowManager.FLAG_LAYOUT_IN_SCREEN)
                window.addFlags(WindowManager.FLAG_LAYOUT_NO_LIMITS)

                try:
                    window.setDecorFitsSystemWindows(False)
                except:
                    pass

                uiOptions = (
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY |
                    View.SYSTEM_UI_FLAG_LAYOUT_STABLE |
                    View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION |
                    View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN |
                    View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
                    View.SYSTEM_UI_FLAG_FULLSCREEN |
                    View.SYSTEM_UI_FLAG_LOW_PROFILE
                )

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
                    except:
                        pass

                decorView.setSystemUiVisibility(uiOptions)

                if BuildVersion.SDK_INT >= 28:
                    try:
                        params = window.getAttributes()
                        params.layoutInDisplayCutoutMode = 1
                        window.setAttributes(params)
                    except:
                        pass

                # Создаём НОВЫЙ listener и сохраняем
                new_listener = XiaomiUiListener(uiOptions)
                webview_ref['ui_listener'] = new_listener
                decorView.setOnSystemUiVisibilityChangeListener(new_listener)
                decorView.setFitsSystemWindows(False)

            except Exception as e:
                print(f"Fullscreen error: {e}")

    # --- WebView Runnable (с очисткой старых handler'ов) ---
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
                    print("Activity is None")
                    return

                # Удаляем старый WebView, если есть
                old_wv = webview_ref.get('view')
                if old_wv:
                    parent = old_wv.getParent()
                    if parent:
                        parent.removeView(old_wv)
                    webview_ref['view'] = None

                # Удаляем старый back handler (чтобы не висел)
                webview_ref['back_handler'] = None

                # Создаём новый WebView
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
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY |
                    View.SYSTEM_UI_FLAG_LOW_PROFILE
                )
                wv.clearFocus()

                wv.setWebViewClient(WebViewClient())

                # Back button handler (новый)
                class BackHandler(PythonJavaClass):
                    __javainterfaces__ = ['android/view/View$OnKeyListener']
                    
                    @java_method('(Landroid/view/View;ILandroid/view/KeyEvent;)Z')
                    def onKey(self, v, keyCode, event):
                        if keyCode == 4 and event.getAction() == 0:
                            if wv.canGoBack():
                                wv.goBack()
                                return True
                        return False

                back_handler = BackHandler()
                wv.setOnKeyListener(back_handler)
                webview_ref['back_handler'] = back_handler

                # Загружаем HTML
                wv.loadDataWithBaseURL('http://localhost:5000/', self.html_content,
                                       'text/html', 'UTF-8', None)

                # Добавляем на экран
                params = ViewGroupLayoutParams(
                    ViewGroupLayoutParams.MATCH_PARENT,
                    ViewGroupLayoutParams.MATCH_PARENT
                )
                activity.addContentView(wv, params)
                webview_ref['view'] = wv

            except Exception as e:
                print(f"Error adding WebView: {e}")

    # --- Runnable для удаления WebView ---
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
                    webview_ref['back_handler'] = None
            except Exception as e:
                print(f"Error removing WebView: {e}")

# --- Kivy App ---
class TestApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._fs_runnable = None
        self.flask_thread = None
        self._redmi_mode = False

        if AndroidAvailable:
            try:
                model = Build.MODEL.lower()
                manufacturer = Build.MANUFACTURER.lower()
                self._redmi_mode = ('redmi' in model or 'xiaomi' in manufacturer)
                print(f"Device: {manufacturer} {model}, Redmi mode: {self._redmi_mode}")
            except:
                pass

    def build(self):
        return Widget()

    def on_start(self):
        self.start_flask()
        Clock.schedule_once(self.initial_android_setup, 2.5)

    def initial_android_setup(self, dt):
        if not AndroidAvailable:
            return
        activity = PythonActivity.mActivity
        if not activity:
            Clock.schedule_once(self.initial_android_setup, 1.0)
            return
        try:
            activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)
            self.set_fullscreen()
            self.open_webview()
        except Exception as e:
            print(f"Safe Init Error: {e}")

    def set_fullscreen(self, *args):
        if AndroidAvailable and PythonActivity.mActivity:
            if self._fs_runnable is None:
                self._fs_runnable = FullscreenRunnable()
            PythonActivity.mActivity.runOnUiThread(self._fs_runnable)

    def aggressive_fullscreen_fix(self, dt):
        if not AndroidAvailable:
            return False
        try:
            activity = PythonActivity.mActivity
            if not activity:
                return True
            window = activity.getWindow()
            decorView = window.getDecorView()
            current_ui = decorView.getSystemUiVisibility()
            desired_ui = (
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY |
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE |
                View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION |
                View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN |
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
                View.SYSTEM_UI_FLAG_FULLSCREEN |
                View.SYSTEM_UI_FLAG_LOW_PROFILE
            )
            if (current_ui & View.SYSTEM_UI_FLAG_FULLSCREEN) == 0:
                print("Redmi reset detected - reapplying fullscreen")
                decorView.setSystemUiVisibility(desired_ui)
                WindowManager = autoclass('android.view.WindowManager$LayoutParams')
                window.addFlags(WindowManager.FLAG_FULLSCREEN)
                window.addFlags(WindowManager.FLAG_LAYOUT_IN_SCREEN)
                window.addFlags(WindowManager.FLAG_LAYOUT_NO_LIMITS)
        except Exception as e:
            print(f"Aggressive fix error: {e}")
        return True

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
        if self._redmi_mode:
            Clock.schedule_once(lambda dt: self.set_fullscreen(), 0.3)
            Clock.schedule_once(self.aggressive_fullscreen_fix, 0.5)

    def fix_webview_fullscreen(self, *args):
        if not AndroidAvailable:
            return
        def apply_flags():
            try:
                wv = webview_ref.get('view')
                if wv:
                    uiOptions = (
                        View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY |
                        View.SYSTEM_UI_FLAG_LAYOUT_STABLE |
                        View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION |
                        View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN |
                        View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
                        View.SYSTEM_UI_FLAG_FULLSCREEN |
                        View.SYSTEM_UI_FLAG_LOW_PROFILE
                    )
                    wv.setSystemUiVisibility(uiOptions)
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
                print("WebView fullscreen fix error:", e)

        class RunnableFix(PythonJavaClass):
            __javainterfaces__ = ['java/lang/Runnable']
            @java_method('()V')
            def run(self):
                apply_flags()

        PythonActivity.mActivity.runOnUiThread(RunnableFix())

    def check_and_restore_webview(self, dt):
        if AndroidAvailable:
            wv = webview_ref.get('view')
            if wv is None or wv.getParent() is None:
                logger.info("WebView was destroyed, recreating...")
                self.open_webview()
            else:
                logger.debug("WebView is alive and attached")

    def on_resume(self):
        if not AndroidAvailable:
            return
        print("App resumed - reapplying fullscreen")
        Clock.unschedule(self.set_fullscreen)
        Clock.unschedule(self.aggressive_fullscreen_fix)

        self.set_fullscreen()

        if self._redmi_mode:
            intervals = [0.1, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 2.5, 3.0]
            for interval in intervals:
                Clock.schedule_once(lambda dt: self.set_fullscreen(), interval)
            Clock.schedule_interval(self.aggressive_fullscreen_fix, 0.5)
        else:
            for interval in [0.3, 1.0, 2.0]:
                Clock.schedule_once(lambda dt: self.set_fullscreen(), interval)

        self.fix_webview_fullscreen()
        Clock.schedule_once(lambda dt: self.fix_webview_fullscreen(), 0.5)
        Clock.schedule_once(lambda dt: self.fix_webview_fullscreen(), 1.0)
        Clock.schedule_once(self.check_and_restore_webview, 1.5)

        try:
            if PythonActivity.mActivity:
                PythonActivity.mActivity.setRequestedOrientation(
                    ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
                )
        except Exception as e:
            print(f"Orientation error: {e}")

    def on_pause(self):
        if AndroidAvailable:
            Clock.unschedule(self.set_fullscreen)
            Clock.unschedule(self.aggressive_fullscreen_fix)
        return True

    def on_stop(self):
        if AndroidAvailable:
            PythonActivity.mActivity.runOnUiThread(_RemoveWebViewRunnable())

if __name__ == '__main__':
    TestApp().run()
