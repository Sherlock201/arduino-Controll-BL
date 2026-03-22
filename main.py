from kivy.app import App
from kivy.clock import Clock
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.popup import Popup

import threading
import os
import netifaces
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# pyjnius
try:
    from jnius import autoclass, PythonJavaClass, java_method
    from android.runnable import run_on_ui_thread
    AndroidAvailable = True
except Exception as e:
    AndroidAvailable = False
    print("pyjnius not available:", e)

# -------------------- HTTP Server --------------------

www_dir = os.path.join(os.getcwd(), 'www')

class HTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP сервер для API"""
    
    def do_GET(self):
        """Обработка GET запросов"""
        try:
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            query_params = parse_qs(parsed_path.query)
            
            print(f"[HTTP] GET {path}")
            
            # API endpoints
            if path == '/ping':
                self.send_json({"status": "pong"})
            
            elif path == '/bt_connect':
                app_instance = App.get_running_app()
                Clock.schedule_once(lambda dt: app_instance.show_device_selector())
                self.send_json({"status": "processing"})
            
            elif path == '/bt_disconnect':
                app_instance = App.get_running_app()
                Clock.schedule_once(lambda dt: app_instance.disconnect_bt())
                self.send_json({"status": "disconnected"})
            
            elif path == '/send':
                cmd = query_params.get('cmd', [''])[0]
                print(f"[HTTP] SEND: {cmd}")
                app_instance = App.get_running_app()
                app_instance.send_to_bt(cmd)
                self.send_json({"status": "ok", "cmd": cmd})
            
            # Главная страница
            elif path == '/' or path == '':
                self.serve_html_file('index.html')
            
            # Статические файлы
            else:
                self.serve_static_file(path.lstrip('/'))
        
        except Exception as e:
            print(f"[HTTP] Error: {e}")
            self.send_error(500, str(e))
    
    def do_OPTIONS(self):
        """Обработка CORS preflight запросов"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def serve_html_file(self, filename):
        """Подай HTML файл"""
        try:
            index_path = os.path.join(www_dir, filename)
            
            if not os.path.exists(index_path):
                self.send_error(404, "File not found")
                return
            
            with open(index_path, 'r', encoding='utf-8') as f:
                html = f.read()
            
            # Подставь реальный IP для fetch запросов
            ip = get_local_ip()
            html = html.replace('{{ SERVER_IP }}', ip)
            html = html.replace('{{SERVER_IP}}', ip)
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            
        except Exception as e:
            print(f"[HTTP] serve_html_file error: {e}")
            self.send_error(500, str(e))
    
    def serve_static_file(self, filename):
        """Подай статические файлы"""
        try:
            file_path = os.path.join(www_dir, filename)
            file_path = os.path.abspath(file_path)
            
            if not file_path.startswith(www_dir):
                self.send_error(403, "Access denied")
                return
            
            if not os.path.exists(file_path):
                self.send_error(404, "File not found")
                return
            
            mime_types = {
                '.html': 'text/html',
                '.css': 'text/css',
                '.js': 'application/javascript',
                '.json': 'application/json',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.svg': 'image/svg+xml',
                '.ico': 'image/x-icon',
            }
            
            ext = os.path.splitext(file_path)[1].lower()
            mime_type = mime_types.get(ext, 'application/octet-stream')
            
            with open(file_path, 'rb') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', mime_type)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
            
        except Exception as e:
            print(f"[HTTP] serve_static_file error: {e}")
            self.send_error(500, str(e))
    
    def send_json(self, data):
        """Отправь JSON ответ"""
        json_data = json.dumps(data)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json_data.encode('utf-8'))
    
    def log_message(self, format, *args):
        """Отключи стандартный лог"""
        pass

def get_local_ip():
    """Получи локальный IP в сети"""
    try:
        for iface in netifaces.interfaces():
            if iface.startswith('wlan') or iface.startswith('eth'):
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    return addrs[netifaces.AF_INET][0]['addr']
    except:
        pass
    return '127.0.0.1'

def run_http_server():
    """Запусти HTTP сервер"""
    print("[HTTP] Начинаю запуск...")
    ip = get_local_ip()
    print(f"[HTTP] IP адрес: {ip}")
    print(f"[HTTP] www директория: {www_dir}")
    print(f"[HTTP] Статус файлов в www/:")
    
    if os.path.exists(www_dir):
        for f in os.listdir(www_dir):
            print(f"[HTTP]   - {f}")
    else:
        print("[HTTP]   ОШИБКА: www директория не найдена!")
    
    try:
        server = HTTPServer(('0.0.0.0', 5000), HTTPRequestHandler)
        print(f"[HTTP] Сервер запущен на http://{ip}:5000")
        print("[HTTP] Слушаю на 0.0.0.0:5000")
        server.serve_forever()
    except Exception as e:
        print(f"[HTTP] ОШИБКА при запуске сервера: {e}")
        import traceback
        traceback.print_exc()

# -------------------- Android WebView --------------------

webview_ref = {'view': None, 'ready': False}

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
                print("[WebView] Fullscreen error:", e)

    class AddWebView(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']

        def __init__(self):
            super().__init__()
            print("[WebView] AddWebView инициализирован")

        @java_method('()V')
        def run(self):
            print("[WebView] run() вызван в UI потоке")
            try:
                activity = PythonActivity.mActivity
                if not activity:
                    print("[WebView] No activity found!")
                    return

                print("[WebView] Creating WebView instance...")
                wv = WebView(activity)
                print("[WebView] WebView created")

                settings = wv.getSettings()
                settings.setJavaScriptEnabled(True)
                settings.setDomStorageEnabled(True)
                settings.setAllowFileAccess(True)
                settings.setAllowContentAccess(True)
                settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW)
                settings.setUseWideViewPort(True)
                settings.setLoadWithOverviewMode(True)
                settings.setSupportZoom(False)

                wv.setVerticalScrollBarEnabled(False)
                wv.setHorizontalScrollBarEnabled(False)

                # Используй реальный IP (не localhost!)
                ip = get_local_ip()
                url = f"http://{ip}:5000/"
                
                print(f"[WebView] Loading URL: {url}")

                wv.loadUrl(url)
                print("[WebView] URL loaded")

                # Используй встроенный WebViewClient без подкласса
                wv.setWebViewClient(WebViewClient())

                params = LayoutParams(
                    LayoutParams.MATCH_PARENT,
                    LayoutParams.MATCH_PARENT
                )

                print("[WebView] Adding to activity...")
                activity.addContentView(wv, params)
                print("[WebView] Added successfully")

                webview_ref['view'] = wv
                webview_ref['ready'] = True
                print("[WebView] WebView fully initialized!")

            except Exception as e:
                print(f"[WebView] ERROR: {e}")
                import traceback
                traceback.print_exc()

# -------------------- Kivy App --------------------

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
        self.http_thread = None
        self.fs = None
        self.socket = None
        self.ostream = None
        
        self.root_box = BoxLayout(orientation='vertical')
        self.status_label = Button(
            text='Загрузка...\nПожалуйста подождите',
            size_hint=(1, 1)
        )
        self.root_box.add_widget(self.status_label)
        
        return self.root_box

    def on_start(self):
        print("[Kivy] on_start вызван")
        self.start_http_server()
        
        # Дай HTTP серверу время поднять
        Clock.schedule_once(self.setup_android, 2.0)

    def setup_android(self, dt):
        print("[Kivy] setup_android вызван")
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
                print("[Kivy] Orientation set to landscape")

            Clock.schedule_once(self.open_webview, 0.5)

        except Exception as e:
            print(f"[Kivy] Setup error: {e}")
            self.status_label.text = f'Setup ошибка: {e}'
            import traceback
            traceback.print_exc()

    def set_fullscreen(self, *args):
        if AndroidAvailable and PythonActivity.mActivity:
            if not self.fs:
                self.fs = FullscreenRunnable()
            print("[Kivy] Setting fullscreen...")
            PythonActivity.mActivity.runOnUiThread(self.fs)

    def start_http_server(self):
        if not self.http_thread:
            print("[Kivy] Starting HTTP server thread...")
            t = threading.Thread(target=run_http_server, daemon=True)
            t.start()
            self.http_thread = t
            print("[Kivy] HTTP server thread started")

    def open_webview(self, dt):
        print("[Kivy] open_webview вызван")
        if not AndroidAvailable:
            print("[Kivy] Android not available")
            return

        try:
            print("[Kivy] Creating AddWebView instance...")
            webview_runnable = AddWebView()
            print("[Kivy] Scheduling on UI thread...")
            
            PythonActivity.mActivity.runOnUiThread(webview_runnable)
            print("[Kivy] Runnable scheduled")
            
            self.status_label.text = 'Инициализация интерфейса...'
            
            Clock.schedule_once(self.check_webview_loaded, 1.0)
            
        except Exception as e:
            print(f"[Kivy] WebView open error: {e}")
            self.status_label.text = f'WebView error: {e}'
            import traceback
            traceback.print_exc()

    def check_webview_loaded(self, dt):
        """Проверь загрузился ли WebView"""
        print(f"[Kivy] check_webview_loaded: ready={webview_ref['ready']}, view={webview_ref['view'] is not None}")
        
        if webview_ref['ready'] and webview_ref['view']:
            print("[Kivy] WebView loaded successfully!")
            self.status_label.text = ''
            self.status_label.size_hint = (0, 0)
        else:
            print("[Kivy] WebView not ready yet, retrying...")
            self.status_label.text = 'WebView не готов...'
            Clock.schedule_once(self.check_webview_loaded, 1.0)

    # --- Методы управления Bluetooth ---
    
    def show_device_selector(self):
        if not AndroidAvailable: 
            print("[Kivy] Bluetooth доступен только на Android")
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
            print(f"[Kivy] Selector error: {e}")

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
        if self.ostream:
            try:
                self.ostream.write(data.encode())
                self.ostream.flush()
            except:
                self.update_status_js("Связь потеряна")
                self.socket = None

    def update_status_js(self, text):
        if webview_ref['view']:
            def run_js():
                try:
                    webview_ref['view'].evaluateJavascript(
                        f"if(document.querySelector('.status')) document.querySelector('.status').textContent = '{text}';", 
                        None
                    )
                except:
                    pass
            try:
                PythonActivity.mActivity.runOnUiThread(run_js)
            except:
                pass

# --------------------

if __name__ == '__main__':
    TestApp().run()
