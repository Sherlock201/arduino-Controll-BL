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
            settings = wv.getSettings()
            settings.setJavaScriptEnabled(True)
            settings.setDomStorageEnabled(True)
            settings.setAllowFileAccess(True)
            settings.setAllowContentAccess(True)
            settings.setMixedContentMode(0) 

            # --- ХАК ДЛЯ ЗАГРУЗКИ БЕЗ ОШИБКИ CLEARTEXT ---
            # Читаем содержимое index.html из папки www напрямую в Python
            try:
                # В buildozer.spec source.dir = . , значит www рядом с main.py
                www_path = os.path.join(os.getcwd(), 'www', 'index.html')
                if os.path.exists(www_path):
                    with open(www_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                else:
                    html_content = "<html><body><h1>index.html not found in /www</h1></body></html>"
            except Exception as e:
                html_content = f"<html><body><h1>Error reading file: {str(e)}</h1></body></html>"

            # Вместо loadUrl используем загрузку данных.
            # baseUrl 'http://localhost:5000/' позволит JS делать fetch/XHR к Flask,
            # но сама страница откроется моментально и без проверки безопасности.
            wv.loadDataWithBaseURL('http://localhost:5000/', html_content, 'text/html', 'UTF-8', None)
            # ---------------------------------------------

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
        #self.start_flask()

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
        
    def on_start(self):
        # Запускаем Flask через секунду после того, как Kivy отрисует интерфейс
        Clock.schedule_once(lambda dt: self.start_flask(), 1)
        
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

        # Правильный вызов: создаем объект Runnable и передаем его в UI поток
        #url = 'http://127.0.0.1:5000' # лучше 127.0.0.1
        url = 'http://127.0.0.1'
        
        # Сначала меняем ориентацию на альбомную
        ActivityInfo = autoclass('android.content.pm.ActivityInfo')
        PythonActivity.mActivity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE)
        
        # Теперь запускаем WebView
        runnable = _AddWebViewRunnable(url)
        PythonActivity.mActivity.runOnUiThread(runnable)
        self._update_label("WebView opened.")

    def close_webview(self):
        if not AndroidAvailable:
            self._update_label("Nothing to close.")
            return
        
        # Возвращаем вертикальный режим
        ActivityInfo = autoclass('android.content.pm.ActivityInfo')
        PythonActivity.mActivity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)
        
        # Удаляем WebView
        PythonActivity.mActivity.runOnUiThread(_RemoveWebViewRunnable())
        self._update_label("WebView removed.")

    def on_stop(self):
        # удалить WebView при закрытии
        if AndroidAvailable:
            PythonActivity.mActivity.runOnUiThread(_RemoveWebViewRunnable())

if __name__ == '__main__':
    TestApp().run()



