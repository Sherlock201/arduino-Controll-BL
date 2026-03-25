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
from flask import Flask, jsonify, request
from jnius import autoclass

try:
    from jnius import autoclass, PythonJavaClass, java_method
    from android.runnable import run_on_ui_thread
    from android.storage import app_storage_path 
    AndroidAvailable = True
except Exception as e:
    AndroidAvailable = False
    print("pyjnius not available:", e)

# -------------------- Flask Server (только для API) --------------------

app = Flask(__name__)

@app.after_request
def after_request(response):
    """Добавляем CORS заголовки ко всем ответам"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

@app.route('/ping', methods=['GET', 'OPTIONS'])
def ping():
    return jsonify({"status": "pong"})

@app.route('/bt_connect', methods=['GET', 'OPTIONS'])
def bt_connect():
    app_instance = App.get_running_app()
    Clock.schedule_once(lambda dt: app_instance.show_device_selector())
    return jsonify({"status": "processing"})

@app.route('/bt_disconnect', methods=['GET', 'OPTIONS'])
def bt_disconnect():
    app_instance = App.get_running_app()
    Clock.schedule_once(lambda dt: app_instance.disconnect_bt())
    return jsonify({"status": "disconnected"})

@app.route('/send', methods=['GET', 'POST', 'OPTIONS'])
def send():
    # Пытаемся взять cmd из GET (args) или POST (form)
    cmd = request.args.get('cmd') or request.form.get('cmd')
    
    if cmd:
        app_instance = App.get_running_app()
        Clock.schedule_once(lambda dt: app_instance.send_to_bt(cmd))
    
    return jsonify({"status": "ok"}), 200

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

def run_flask_server():
    """Запусти Flask сервер ТОЛЬКО для API"""
    print("[HTTP] Начинаю запуск...")
    ip = get_local_ip()
    print(f"[HTTP] IP адрес: {ip}")

    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except Exception as e:
        print(f"[HTTP] ОШИБКА: {e}")

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

                settings = wv.getSettings()
                settings.setJavaScriptEnabled(True)
                settings.setDomStorageEnabled(True)
                settings.setAllowFileAccess(True)
                settings.setAllowContentAccess(True)
                settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW)
                settings.setAllowFileAccessFromFileURLs(True)
                settings.setAllowUniversalAccessFromFileURLs(True)
                settings.setUseWideViewPort(True)
                settings.setLoadWithOverviewMode(True)
                settings.setSupportZoom(False)

                wv.setVerticalScrollBarEnabled(False)
                wv.setHorizontalScrollBarEnabled(False)

                # Загружаем локальный HTML из папки www
                base_path = os.path.abspath(os.path.dirname(__file__))
                index_path = os.path.join(base_path, "www", "index.html")
                asset_url = f"file://{index_path}"
                
                print(f"[WebView] Loading from asset: {asset_url}")

                wv.loadUrl(asset_url)
                print("[WebView] URL loaded")

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
        
        Clock.schedule_once(self.setup_android, 1.0)

    def set_webview_visibility(self, visible):
        if not AndroidAvailable or not webview_ref['view']:
            return
        PythonActivity.mActivity.runOnUiThread(
            lambda: webview_ref['view'].setVisibility(
                View.VISIBLE if visible else View.GONE
            )
        )
    
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

    def set_fullscreen(self, *args):
        if AndroidAvailable and PythonActivity.mActivity:
            if not self.fs:
                self.fs = FullscreenRunnable()
            print("[Kivy] Setting fullscreen...")
            PythonActivity.mActivity.runOnUiThread(self.fs)

    def start_http_server(self):
        if not self.http_thread:
            print("[Kivy] Starting Flask server thread...")
            t = threading.Thread(target=run_flask_server, daemon=True)
            t.start()
            self.http_thread = t

    def open_webview(self, dt):
        print("[Kivy] open_webview вызван")
        if not AndroidAvailable:
            return

        try:
            webview_runnable = AddWebView()
            PythonActivity.mActivity.runOnUiThread(webview_runnable)
            
            self.status_label.text = 'Инициализация...'
            Clock.schedule_once(self.check_webview_loaded, 1.0)
            
        except Exception as e:
            print(f"[Kivy] WebView open error: {e}")
            self.status_label.text = f'WebView error: {e}'

    def check_webview_loaded(self, dt):
        if webview_ref['ready'] and webview_ref['view']:
            print("[Kivy] WebView loaded!")
            self.status_label.text = ''
            self.status_label.size_hint = (0, 0)
        else:
            self.status_label.text = 'WebView не готов...'
            Clock.schedule_once(self.check_webview_loaded, 1.0)

    # --- Bluetooth методы ---
    def show_error_popup(self, title, message):
        layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        layout.add_widget(Label(text=message, halign='center'))
        
        close_btn = Button(text="OK", size_hint=(1, 0.4))
        layout.add_widget(close_btn)
        
        error_popup = Popup(
            title=title, 
            content=layout, 
            size_hint=(0.8, 0.4),
            auto_dismiss=False # Чтобы не закрыли случайно тапнув мимо
        )
        
        # При закрытии этого окна возвращаем WebView
        close_btn.bind(on_release=error_popup.dismiss)
        error_popup.bind(on_dismiss=self.restore_webview)
        
        error_popup.open()
        
    def show_device_selector(self):
        if not AndroidAvailable: 
            return
    
        print("[Kivy] show_device_selector called")
    
        try:
            # Скрываем WebView
            if webview_ref['view']:
                print("[Kivy] Hiding WebView")
                self.set_webview_visibility(False)
        
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            adapter = BluetoothAdapter.getDefaultAdapter()

            # ПРОВЕРКА: Если Bluetooth выключен
            if adapter is None or not adapter.isEnabled():
                # 1. Отправляем текст в JS (если нужно)
                self.update_status_js("Включите Bluetooth!")
                # 2. Показываем Kivy-уведомление (Popup), чтобы пользователь понял причину
                self.show_error_popup("Ошибка", "Пожалуйста, включите Bluetooth в настройках телефона.")
                # 3. WebView восстановится автоматически при закрытии этого попапа (см. ниже)
                return
                
            if not adapter.isEnabled():
                self.update_status_js("Включите Bluetooth!")
                return

            paired_devices = adapter.getBondedDevices().toArray()
            device_dict = {}
            for d in paired_devices:
                device_dict[d.getName()] = d.getAddress()
            
            if not device_dict:
                self.update_status_js("Нет устройств")
                return

            content = DeviceSelector(device_dict, self.connect_to_addr)
            self.popup = Popup(title="Выберите устройство", content=content, size_hint=(0.9, 0.9))
        
            # Здесь привязываем обработчик закрытия
            self.popup.bind(on_dismiss=self.restore_webview)
        
            self.popup.open()
            print("[Kivy] Popup opened, WebView hidden")
        
        except Exception as e:
            print(f"[Kivy] Selector error: {e}")
            # Если ошибка, сразу восстанавливаем WebView
            self.restore_webview(None)

    def restore_webview(self, instance):
        """Восстанавливаем видимость WebView после закрытия попапа"""
        if webview_ref['view']:
            print("[Kivy] Restoring WebView")
            self.set_webview_visibility(True)
    
    def connect_to_addr(self, address):
        if hasattr(self, 'popup'):
            self.popup.dismiss()
        self.update_status_js("Подключение...")
        threading.Thread(target=self._bt_thread, args=(address,), daemon=True).start()

    def _monitor_connection(self):
        """Фоновая проверка связи (чтение из сокета)"""
        try:
            istream = self.socket.getInputStream()
            while self.socket and self.ostream:
                # read() блокируется до прихода данных или ошибки
                # Если робот выключится, read() выкинет Exception
                res = istream.read()
                if res == -1: # Конец потока
                    break
        except Exception as e:
            print(f"[BT] Monitor: connection lost {e}")
        
        # Если вышли из цикла — значит связи нет
        if self.socket: # Проверяем, не сами ли мы закрыли сокет
            self.socket = None
            self.ostream = None
            self.update_status_js("Связь потеряна")
            
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

            # Запускаем поток мониторинга чтения
            threading.Thread(target=self._monitor_connection, daemon=True).start()
            
        except Exception as e:
            self.socket = None
            self.ostream = None
            self.update_status_js(f"Ошибка: {str(e)[:15]}")

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
                # Превращаем строку в байтовый массив Python
                # bytearray в pyjnius автоматически преобразуется в Java byte[]
                b_data = bytearray(data, 'utf-8')
            
                self.ostream.write(b_data)
                self.ostream.flush()
                print(f"[BT] Sent: {data.strip()}") 
            except Exception as e:
                print(f"[BT] Error: {e}")
                self.update_status_js("Связь потеряна")
                self.socket = None
                self.ostream = None
        else:
            # Если JS шлет данные, а мы уже знаем, что связи нет
            self.update_status_js("Отключено")

    def update_status_js(self, text):
        if webview_ref['view']:
            def run_js():
                try:
                    # Вызываем JS функцию setStatus, которая и текст меняет, и кнопки
                    script = f"if(typeof setStatus === 'function') setStatus('{text}');"
                    webview_ref['view'].evaluateJavascript(script, None)
                except Exception as e:
                    print(f"JS Eval Error: {e}")
            
            # Всегда выполняем в UI потоке Android
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                PythonActivity.mActivity.runOnUiThread(run_js)
            except:
                pass

if __name__ == '__main__':
    TestApp().run()
