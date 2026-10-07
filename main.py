from kivy.app import App
from kivy.clock import Clock
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup

import threading
import os
import time
import netifaces
import json
from flask import Flask, jsonify, request

try:
    from jnius import autoclass, PythonJavaClass, java_method
    from android.runnable import run_on_ui_thread
    from android.storage import app_storage_path 
    from android.permissions import request_permissions, Permission
    
    AndroidAvailable = True
except Exception as e:
    AndroidAvailable = False
    print("pyjnius not available:", e)

# -------------------- BLE Listener (Pyjnius Interface) --------------------

if AndroidAvailable:
    class BleListenerImpl(PythonJavaClass):
        __javainterfaces__ = ['org/sherlock201/spble/MyGattCallback$BleListener']
        __javacontext__ = 'app'

        def __init__(self, app_instance):
            super().__init__()
            self.app = app_instance

        @java_method('()V')
        def onConnected(self):
            print("[BLE] Connected to GATT server, waiting for services...")

        @java_method('()V')
        def onDisconnected(self):
            print("[BLE] Disconnected from GATT server")
            self.app.handle_ble_disconnect()

        @java_method('(Landroid/bluetooth/BluetoothGatt;I)V')
        def onServicesDiscovered(self, gatt, status):
            if status == 0:  # GATT_SUCCESS = 0
                print("[BLE] Services discovered successfully")
                self.app.handle_ble_services_discovered(gatt)
            else:
                print(f"[BLE] Service discovery failed with status: {status}")
                self.app.handle_ble_error(f"GATT discovery error: {status}")

        @java_method('(Ljava/lang/String;)V')
        def onError(self, message):
            print(f"[BLE] Error: {message}")
            self.app.handle_ble_error(message)

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

        # Переменные управления подключением
        self.conn_mode = None  # 'classic' или 'ble'
        self.gatt = None
        self.ble_char = None
        self.ble_event = None
        self.ble_error_msg = ""
        self._internal_disconnect = False

        # --- Предварительная загрузка JNI ---
        if AndroidAvailable:
            try:
                self.ble_listener = BleListenerImpl(self)
                self.MyGattCallbackClass = autoclass('org.sherlock201.spble.MyGattCallback')
            except Exception as e:
                print(f"[Init] BLE JNI Error: {e}")
                self.ble_listener = None
                self.MyGattCallbackClass = None
        else:
            self.ble_listener = None
            self.MyGattCallbackClass = None
        # -------------------------------------------------
        
        self.root_box = BoxLayout(orientation='vertical')
        self.status_label = Button(
            text='Загрузка...\nПожалуйста подождите',
            size_hint=(1, 1)
        )
        self.root_box.add_widget(self.status_label)
        
        return self.root_box

    def on_start(self):
        print("[Kivy] on_start вызван")
    
        # 1. Запрашиваем разрешения у пользователя (для Android 12+)
        if AndroidAvailable:
            request_permissions([
                Permission.BLUETOOTH_CONNECT,
                Permission.BLUETOOTH_SCAN,
                Permission.ACCESS_FINE_LOCATION,
                Permission.ACCESS_COARSE_LOCATION
            ])

        # 2. Твоя существующая логика
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

        # Сбрасываем старые подключения
        self.disconnect_bt()

        # Пауза, чтобы старый GATT успел освободиться, а callback отработал
        time.sleep(0.5)

        threading.Thread(target=self._bt_thread, args=(address,), daemon=True).start()

    def _monitor_connection(self):
        """Фоновая проверка связи (чтение из сокета) для Classic Bluetooth"""
        try:
            istream = self.socket.getInputStream()
            while self.socket and self.ostream and self.conn_mode == 'classic':
                # read() блокируется до прихода данных или ошибки
                res = istream.read()
                if res == -1: # Конец потока
                    break
        except Exception as e:
            print(f"[BT] Monitor Classic lost connection: {e}")
        
        if self.conn_mode == 'classic':
            self.conn_mode = None
            self.socket = None
            self.ostream = None
            self.update_status_js("Связь потеряна")

    # --- Помощники BLE Callback ---
    def handle_ble_services_discovered(self, gatt):
        """Автоматический поиск характеристики с поддержкой записи"""
        found_char = None
        services = gatt.getServices().toArray()
        
        for service in services:
            characteristics = service.getCharacteristics().toArray()
            for char in characteristics:
                props = char.getProperties()
                # 8 = WRITE, 4 = WRITE_NO_RESPONSE
                if (props & 8) or (props & 4):
                    found_char = char
                    break
            if found_char:
                break
                
        if found_char:
            self.ble_char = found_char
            if self.ble_event:
                self.ble_event.set()
        else:
            self.handle_ble_error("No write characteristic found")

        self.gatt = gatt
        
        # Обновляем WebView - кнопки станут активными!
        self.update_status_js("Подключено")
        print("[BLE] Services ready, UI updated to 'Подключено'")

    def handle_ble_disconnect(self):
        """Освобождение ресурсов BLE только после подтверждения разрыва от Android"""
        print("[BLE] handle_ble_disconnect called")

        # Если это внутренний disconnect от _try_ble_connect — не трогаем self.gatt,
        # он уже сброшен и закрыт вручную
        if self._internal_disconnect:
            print("[BLE] Internal disconnect - skipping cleanup")
            return

        if self.gatt:
            try:
                self.gatt.close()
                print("[BLE] GATT client successfully closed.")
            except Exception as e:
                print(f"[BLE] Error closing GATT: {e}")
            self.gatt = None

        self.conn_mode = None
        self.ble_char = None
        self.update_status_js("Отключено")

        # Разблокируем поток, если он завис в ожидании подключения
        if self.ble_event:
            self.ble_event.set()

    def handle_ble_error(self, message):
        self.ble_error_msg = message
        if self.ble_event:
            self.ble_event.set()
        self.update_status_js(f"Ошибка: {str(message)[:15]}")

    # --- Один цикл BLE-подключения ---
    def _try_ble_connect(self, device):
        """Один цикл BLE-подключения. True при успехе.
           При провале сам закрывает GATT и возвращает False.
           При успехе self.gatt остаётся живым, self.ble_char заполнен."""
        self.ble_event = threading.Event()
        self.ble_error_msg = ""
        self.ble_char = None

        try:
            activity = PythonActivity.mActivity

            if not self.MyGattCallbackClass or not self.ble_listener:
                raise Exception("BLE classes not initialized on main thread")

            callback_instance = self.MyGattCallbackClass(self.ble_listener)

            try:
                self.gatt = device.connectGatt(activity, False, callback_instance, 2)
            except:
                self.gatt = device.connectGatt(activity, False, callback_instance)

            if not self.gatt:
                raise Exception("Failed to invoke connectGatt")

            success = self.ble_event.wait(timeout=4.0)

            if success and self.ble_char:
                return True

            print(f"[BT] BLE cycle failed: {self.ble_error_msg or 'timeout'}")
        except Exception as e:
            print(f"[BT] BLE cycle error: {e}")

        # --- Провал: рвём и чистим ---
        if self.gatt:
            gatt_to_kill = self.gatt
            self.gatt = None
            self.conn_mode = None
            self._internal_disconnect = True
            try:
                gatt_to_kill.disconnect()
            except:
                pass
            time.sleep(0.3)
            try:
                gatt_to_kill.close()
            except:
                pass
            self.ble_char = None
            self._internal_disconnect = False
            time.sleep(0.5)

        return False

    # --- Главная каскадная логика (BLE retry -> Classic -> Error) ---
    def _bt_thread(self, address):
        BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
        UUID = autoclass('java.util.UUID')
        adapter = BluetoothAdapter.getDefaultAdapter()
        device = adapter.getRemoteDevice(address)

        # --- Определение типа устройства ---
        try:
            dev_type = device.getType()
            # 0=UNKNOWN, 1=CLASSIC, 2=LE, 3=DUAL
            print(f"[BT] device.getType() = {dev_type}")
        except Exception as e:
            dev_type = 0
            print(f"[BT] getType() failed: {e}")

        want_ble_first = (dev_type != 1)  # всё кроме чистого CLASSIC
        want_classic    = (dev_type != 2)  # всё кроме чистого LE

        # --------------------------------------------------------
        # ШАГ 1: BLE (GATT) с ретраями (до 3 полных циклов)
        # --------------------------------------------------------
        if want_ble_first:
            max_cycles = 3
            for cycle in range(1, max_cycles + 1):
                print(f"[BT] BLE cycle #{cycle}/{max_cycles}")
                self.update_status_js(f"Подключение: BLE ({cycle}/{max_cycles})...")

                if self._try_ble_connect(device):
                    self.conn_mode = 'ble'
                    self.update_status_js("Подключено (BLE)")
                    print(f"[BT] Connected via BLE on cycle #{cycle}!")
                    return

                time.sleep(1.0)

            if not want_classic:
                print("[BT] Device is LE-only, all BLE cycles failed.")
                self.conn_mode = None
                self.update_status_js("Ошибка подключения")
                Clock.schedule_once(lambda dt: self.show_error_popup(
                    "Ошибка подключения",
                    "BLE-устройство не ответило после 3 попыток."
                ))
                return

            # Даём адаптеру передохнуть перед Classic
            print("[BT] Ждём 2 секунды перед Classic...")
            time.sleep(2.0)

        # --------------------------------------------------------
        # ШАГ 2: Classic (RFCOMM)
        # --------------------------------------------------------
        if want_classic:
            print("[BT] Step 2: Trying Classic Bluetooth...")
            self.update_status_js("Подключение: Classic...")
            try:
                uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
                self.socket = device.createRfcommSocketToServiceRecord(uuid)
                self.socket.connect()
                self.ostream = self.socket.getOutputStream()

                self.conn_mode = 'classic'
                self.update_status_js("Подключено (Classic)")
                print("[BT] Connected via Classic Bluetooth!")

                # Запускаем поток мониторинга чтения
                threading.Thread(target=self._monitor_connection, daemon=True).start()
                return
            except Exception as e_classic:
                print(f"[BT] Classic Bluetooth failed: {e_classic}")
                if self.socket:
                    try:
                        self.socket.close()
                    except:
                        pass
                self.socket = None
                self.ostream = None
                try:
                    adapter.cancelDiscovery()
                except:
                    pass

        # --------------------------------------------------------
        # ШАГ 3: Оба не удались
        # --------------------------------------------------------
        print("[BT] All connection attempts failed.")
        self.conn_mode = None
        self.update_status_js("Ошибка подключения")
        Clock.schedule_once(
            lambda dt: self.show_error_popup(
                "Ошибка подключения",
                "Не удалось подключиться ни по BLE, ни по Classic."
            )
        )

    def disconnect_bt(self):
        try:
            # Принудительно закрываем сокет (прерывает зависание connect)
            if self.socket:
                self.socket.close()
            self.socket = None
            self.ostream = None

            # Отключаем GATT. close() НЕ вызываем — он придёт в callback
            # handle_ble_disconnect() и там корректно закроет клиент.
            if self.gatt:
                try:
                    self.gatt.disconnect()
                except:
                    pass
        except Exception as e:
            print(f"[BT] Disconnect error: {e}")

        self.conn_mode = None
        self.ble_char = None
        self.update_status_js("Отключено")

    def send_to_bt(self, data):
        if self.conn_mode == 'classic' and self.ostream:
            try:
                # Превращаем строку в байтовый массив Python
                # bytearray в pyjnius автоматически преобразуется в Java byte[]
                b_data = bytearray(data, 'utf-8')
                self.ostream.write(b_data)
                self.ostream.flush()
                print(f"[BT Classic] Sent: {data.strip()}")
            except Exception as e:
                print(f"[BT Classic] Send Error: {e}")
                self.update_status_js("Связь потеряна")
                self.socket = None
                self.ostream = None
                self.conn_mode = None

        elif self.conn_mode == 'ble' and self.gatt and self.ble_char:
            try:
                b_data = bytearray(data, 'utf-8')
                self.ble_char.setValue(b_data)
                self.gatt.writeCharacteristic(self.ble_char)
                print(f"[BT BLE] Sent: {data.strip()}")
            except Exception as e:
                print(f"[BT BLE] Send Error: {e}")
                self.update_status_js("Связь потеряна")
                self.disconnect_bt()

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
