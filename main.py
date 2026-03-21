from kivy.app import App
from kivy.clock import Clock
from kivy.uix.widget import Widget

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.recycleview import RecycleView
from kivy.uix.popup import Popup

import threading
import os

# Flask
from flask import Flask, send_from_directory, render_template_string
from flask import request, jsonify

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

@app.route('/bt_connect')
def bt_connect():
    # Сигнализируем Kivy открыть список устройств
    app_instance = App.get_running_app()
    Clock.schedule_once(lambda dt: app_instance.show_device_selector())
    return jsonify({"status": "processing"})

@app.route('/bt_disconnect')
def bt_disconnect():
    app_instance = App.get_running_app()
    Clock.schedule_once(lambda dt: app_instance.disconnect_bt())
    return jsonify({"status": "disconnected"})

@app.route('/send')
def send_command():
    cmd = request.args.get('cmd', '')
    app_instance = App.get_running_app()
    # Отправляем данные в поток Bluetooth
    app_instance.send_to_bt(cmd)
    return "ok"

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
class DeviceSelector(BoxLayout):
    def __init__(self, devices, callback, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        self.callback = callback
        for name, address in devices.items():
            btn = Button(text=f"{name}\n{address}", size_hint_y=None, height=100)
            btn.bind(on_release=lambda x, addr=address: self.callback(addr))
            self.add_widget(btn)

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

    # --- Методы управления Bluetooth ---
    
    def show_device_selector(self):
        if not AndroidAvailable: 
            print("Bluetooth доступен только на Android")
            return
        
        try:
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            adapter = BluetoothAdapter.getDefaultAdapter()
            
            if not adapter.isEnabled():
                self.update_status_js("Включите Bluetooth!")
                return

            paired_devices = adapter.getBondedDevices().toArray()
            device_dict = {}
            for d in paired_devices:
                device_dict[d.getName()] = d.getAddress()
                
            if not device_dict:
                self.update_status_js("Нет сопряженных устройств")
                return

            content = DeviceSelector(device_dict, self.connect_to_addr)
            self.popup = Popup(title="Выберите устройство", content=content, size_hint=(0.9, 0.9))
            self.popup.open()
        except Exception as e:
            print(f"Selector error: {e}")

    def connect_to_addr(self, address):
        if hasattr(self, 'popup'):
            self.popup.dismiss()
        self.update_status_js("Подключение...")
        threading.Thread(target=self._bt_thread, args=(address,), daemon=True).start()

    def _bt_thread(self, address):
        try:
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            UUID = autoclass('java.util.UUID')
            adapter = BluetoothAdapter.getDefaultAdapter()
            device = adapter.getRemoteDevice(address)
            
            # Стандартный UUID для HC-06
            uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
            
            self.socket = device.createRfcommSocketToServiceRecord(uuid)
            self.socket.connect()
            self.ostream = self.socket.getOutputStream()
            self.update_status_js("Подключено")
        except Exception as e:
            self.update_status_js(f"Ошибка: {str(e)[:20]}")
            self.socket = None

    def disconnect_bt(self):
        try:
            if self.socket:
                self.socket.close()
            self.socket = None
            self.ostream = None
            self.update_status_js("Отключено")
        except:
            pass

    def send_to_bt(self, data):
        # Пишем в поток, если сокет живой
        if self.ostream:
            try:
                self.ostream.write(data.encode())
                self.ostream.flush()
            except:
                self.update_status_js("Связь потеряна")
                self.socket = None

    def update_status_js(self, text):
        if webview_ref['view']:
            # evaluateJavascript требует запуска в UI потоке Android
            def run_js():
                webview_ref['view'].evaluateJavascript(
                    f"document.querySelector('.status').textContent = '{text}';", 
                    None
                )
            PythonActivity.mActivity.runOnUiThread(run_js)

# --------------------

if __name__ == '__main__':
    TestApp().run()
