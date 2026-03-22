from kivy.app import App
from kivy.clock import Clock
from kivy.uix.widget import Widget

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.recycleview import RecycleView
from kivy.uix.popup import Popup

import threading
import os
import socket
import netifaces


# Flask
from flask import Flask, send_from_directory, render_template_string
from flask import request, jsonify

# pyjnius
try:
    from jnius import autoclass, PythonJavaClass, java_method
    from android.runnable import run_on_ui_thread
    AndroidAvailable = True
except Exception as e:
    AndroidAvailable = False
    print("pyjnius not available:", e)

# -------------------- Flask --------------------

www_dir = os.path.join(os.getcwd(), 'www')
app = Flask(__name__, static_folder=www_dir, template_folder=www_dir)

def get_local_ip():
    """Получи локальный IP в сети"""
    import socket
    import netifaces
    
    try:
        # Попробуй получить IP из активного интерфейса
        for iface in netifaces.interfaces():
            if iface.startswith('wlan') or iface.startswith('eth'):
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    return addrs[netifaces.AF_INET][0]['addr']
    except:
        pass
    
    # Fallback
    return '127.0.0.1'

@app.route('/')
def index():
    index_path = os.path.join(www_dir, 'index.html')
    if not os.path.exists(index_path):
        return "<h1>No index.html</h1>"
    with open(index_path, 'r', encoding='utf-8') as f:
        html = f.read()

    try:
        ip = get_local_ip()
        print("Определенный ip:", ip)   # теперь будет в логах
        return render_template_string(html, SERVER_IP=ip)
    except Exception as e:
        print("Ошибка в index:", e)
        return f"<h1>Error: {e}</h1>"

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(www_dir, filename)

@app.route('/ping')
def ping():
    print("PING")
    print("Signal ok")
    return "pong"

@app.route('/bt_connect')
def bt_connect():
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
    print("SEND HIT:", cmd)  # чтобы увидеть, доходит ли запрос вообще
    app_instance = App.get_running_app()
    app_instance.send_to_bt(cmd)
    return jsonify({"status": "ok", "cmd": cmd})

def run_flask():
    print("START FLASK ON 0.0.0.0:5000")
    ip = get_local_ip()
    print("Определенный ip:", ip)
    print(app.url_map)
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=True, use_reloader=False)

# -------------------- Android --------------------

webview_ref = {'view': None}

if AndroidAvailable:
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    WebView = autoclass('android.webkit.WebView')
    WebViewClient = autoclass('android.webkit.WebViewClient')
    WebSettings = autoclass('android.webkit.WebSettings')
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
                # ВАЖНО: Разреши cleartext контент
                settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW)

                settings.setUseWideViewPort(True)
                settings.setLoadWithOverviewMode(True)
                settings.setSupportZoom(False)

                wv.setVerticalScrollBarEnabled(False)
                wv.setHorizontalScrollBarEnabled(False)

                # Получи IP
                ip = get_local_ip()
                url = f"http://{ip}:5000/"
            
                print(f"Loading WebView from: {url}")

                # Загрузи URL напрямую (без loadDataWithBaseURL)
                wv.loadUrl(url)

                wv.setWebViewClient(WebViewClient())

                params = LayoutParams(
                    LayoutParams.MATCH_PARENT,
                    LayoutParams.MATCH_PARENT
                )

                activity.addContentView(wv, params)
                webview_ref['view'] = wv

            except Exception as e:
                print(f"WebView error: {e}")
                import traceback
                traceback.print_exc()

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
        
        # Создай видимый контейнер с загрузочным сообщением
        self.root_box = BoxLayout(orientation='vertical')
        self.status_label = Button(
            text='Загрузка...\nПожалуйста подождите',
            size_hint=(1, 1)
        )
        self.root_box.add_widget(self.status_label)
        
        return self.root_box

    def on_start(self):
        # Запусти всё сразу, без больших задержек
        self.start_flask()
        
        # Короче задержка для поднятия Flask
        Clock.schedule_once(self.setup_android, 2.0)

    def setup_android(self, dt):
        if not AndroidAvailable:
            self.status_label.text = 'Ошибка: нет Android'
            return

        try:
            self.set_fullscreen()

            activity = PythonActivity.mActivity
            if activity:
                activity.setRequestedOrientation(
                    ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
                )

            # Открой WebView почти сразу
            Clock.schedule_once(self.open_webview, 0.5)

        except Exception as e:
            print(f"Setup error: {e}")
            self.status_label.text = f'Setup ошибка: {e}'
            import traceback
            traceback.print_exc()

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
            print("[Kivy] Flask thread started")

    def open_webview(self, dt):
        if not AndroidAvailable:
            return

        try:
            print("[Kivy] Opening WebView...")
            self.status_label.text = 'Открываю интерфейс...'
            run_on_ui_thread(AddWebView().run)
            # Обнови статус через 1 сек
            Clock.schedule_once(self.check_webview_loaded, 1.0)
        except Exception as e:
            print(f"[Kivy] WebView open error: {e}")
            self.status_label.text = f'WebView error: {e}'
            import traceback
            traceback.print_exc()

    def check_webview_loaded(self, dt):
        """Проверь загрузился ли WebView"""
        if webview_ref['view']:
            print("[Kivy] WebView loaded successfully!")
            # Скрой загрузочный экран
            self.status_label.text = ''
            self.status_label.size_hint = (0, 0)
        else:
            print("[Kivy] WebView not ready yet")
            self.status_label.text = 'WebView не готов...'
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
