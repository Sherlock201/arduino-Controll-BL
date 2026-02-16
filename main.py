# main.py
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.core.window import Window

import threading
import time
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

# --- Flask app (serves local files in ./www) ---
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
    # bind to localhost: WebView can access http://127.0.0.1:5000
    # threaded=True чтобы не блокировать
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)

# --- WebView handling (Android) ---
webview_ref = {'view': None}  # хранить ссылку на webview, чтобы можно было удалить

if AndroidAvailable:
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    WebView = autoclass('android.webkit.WebView')
    WebViewClient = autoclass('android.webkit.WebViewClient')
    ViewGroupLayoutParams = autoclass('android.view.ViewGroup$LayoutParams')

    class _AddWebViewRunnable(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']
        def __init__(self, url):
            super().__init__()
            self.url = url
        @java_method('()V')
        def run(self):
            activity = PythonActivity.mActivity
            wv = WebView(activity)
            settings = wv.getSettings() # Получаем настройки
            settings.setJavaScriptEnabled(True)
        
            # Она разрешает загрузку контента из любых источников внутри WebView
            settings.setMixedContentMode(0) # 0 = MIXED_CONTENT_ALWAYS_ALLOW
            settings.setAllowFileAccess(True)
            settings.setAllowUniversalAccessFromFileURLs(True)

            wv.setWebViewClient(WebViewClient())
            wv.loadUrl(self.url)
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
                # Получим родителя и удалим view
                parent = wv.getParent()
                if parent:
                    parent.removeView(wv)
                webview_ref['view'] = None

# --- Kivy app (UI) ---
class RootWidget(BoxLayout):
    pass

class TestApp(App):
    def build(self):

        self.flask_thread = None
        # Запускаем Flask один раз при старте приложения
        self.start_flask()

        root = BoxLayout(orientation='vertical', padding=8, spacing=8)
        self.label = Label(text="Status: Flask not started", size_hint=(1, 0.2))
        btn_open = Button(text="Open WebView (local page)", size_hint=(1, 0.1))
        btn_close = Button(text="Close WebView", size_hint=(1, 0.1))

        btn_open.bind(on_release=lambda *a: self.open_webview())
        btn_close.bind(on_release=lambda *a: self.close_webview())

        root.add_widget(self.label)
        root.add_widget(btn_open)
        root.add_widget(btn_close)
        return root

    def start_flask(self):
        if self.flask_thread and self.flask_thread.is_alive():
            return
        t = threading.Thread(target=run_flask, daemon=True)
        t.start()
        self.flask_thread = t
        # даём немного времени серверу подняться
        Clock.schedule_once(lambda dt: self._update_label("Flask running at http://127.0.0.1:5000"), 1.0)

    def _update_label(self, text):
        self.label.text = text

    def open_webview(self):
        if not AndroidAvailable:
            import webbrowser
            webbrowser.open('http://127.0.0.1:5000')
            self._update_label("Opened in external browser (desktop).")
            return

        # Запускаем код, который добавит WebView в UI потоке Android
        url = 'http://localhost:5000/'
        PythonActivity.mActivity.runOnUiThread(_(url))
        self._update_label("WebView opened (local page).")

    def close_webview(self):
        if not AndroidAvailable:
            self._update_label("Nothing to close (desktop).")
            return
        PythonActivity.mActivity.runOnUiThread(_RemoveWebViewRunnable())
        self._update_label("WebView removed.")

    def on_stop(self):
        # удалить WebView при закрытии
        if AndroidAvailable:
            PythonActivity.mActivity.runOnUiThread(_RemoveWebViewRunnable())

if __name__ == '__main__':
    TestApp().run()



