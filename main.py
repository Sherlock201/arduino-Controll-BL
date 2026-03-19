# main.py
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.widget import Widget

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
webview_ref = {'view': None}

if AndroidAvailable:
    # 1. Сначала ВСЕ импорты из Java
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    WebView = autoclass('android.webkit.WebView')
    WebViewClient = autoclass('android.webkit.WebViewClient')
    ViewGroupLayoutParams = autoclass('android.view.ViewGroup$LayoutParams')
    View = autoclass('android.view.View') # Вынеси его сюда, чтобы был доступен везде
    ActivityInfo = autoclass('android.content.pm.ActivityInfo')

    # 2. Теперь описываем классы, которые используют эти импорты
    class FullscreenRunnable(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']
        @java_method('()V')
        def run(self):
            try:
                activity = PythonActivity.mActivity
                if activity:
                    decorView = activity.getWindow().getDecorView()
                    uiOptions = (View.SYSTEM_UI_FLAG_LAYOUT_STABLE 

                               | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION 
                               | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN 
                               | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION 

                               | View.SYSTEM_UI_FLAG_FULLSCREEN 
                               | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY)
                    decorView.setSystemUiVisibility(uiOptions)
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
            View = autoclass('android.view.View')
            settings = wv.getSettings()
            settings.setJavaScriptEnabled(True)
            settings.setDomStorageEnabled(True)
            settings.setAllowFileAccess(True)
            settings.setAllowContentAccess(True)
            settings.setMixedContentMode(0) 

            settings.setUseWideViewPort(True)       # Разрешает использовать viewport из HTML
            settings.setLoadWithOverviewMode(True)  # Умещает контент по ширине экрана
            settings.setSupportZoom(False)          # Отключает системный зум
            # -----------------------------------------
            wv.setInitialScale(0)
            wv.setVerticalScrollBarEnabled(False)
            wv.setHorizontalScrollBarEnabled(False)

            wv.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY)
            
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
        # Возвращаем пустой черный виджет, его никто не увидит
        self._fs_runnable = None 
        return Widget() 
        
    def on_start(self):
        if AndroidAvailable:
            # 1. Сразу фиксируем горизонт (дизайнерский режим)
            ActivityInfo = autoclass('android.content.pm.ActivityInfo')
            PythonActivity.mActivity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)
            
            # 2. Прячем системные кнопки и статус-бар (Fullscreen)
            self.set_fullscreen()
        
        # 3. Запускаем Flask
        self.start_flask()
        
        # 4. Открываем WebView автоматически через 0.5 сек (чтобы Flask "проснулся")
        Clock.schedule_once(lambda dt: self.open_webview(), 0.5)
        
    def set_fullscreen(self, *args):
        if AndroidAvailable:
            # Создаем объект только если его еще нет И активность готова
            if not self._fs_runnable:
                self._fs_runnable = FullscreenRunnable()
            
            activity = PythonActivity.mActivity
            if activity:
                activity.runOnUiThread(self._fs_runnable)

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

        url = 'http://localhost:5000/'
        runnable = _AddWebViewRunnable(url)
        PythonActivity.mActivity.runOnUiThread(runnable)

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

    def on_resume(self):
        if AndroidAvailable:
            # Даем системе 0.2 сек, чтобы она вывела свои панели, 
            # и тут же их "схлопываем" обратно
            Clock.schedule_once(lambda dt: self.set_fullscreen(), 0.2)
            
            # Подтверждаем портрет (если ты решила остаться в нем)
            ActivityInfo = autoclass('android.content.pm.ActivityInfo')
            PythonActivity.mActivity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)

if __name__ == '__main__':
    TestApp().run()



