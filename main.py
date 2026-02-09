from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.core.window import Window

import threading
import time

# Попробуем импортировать Android/pyjnius — если не на Android, просто проигнорируем
try:
    from jnius import autoclass, cast
    AndroidAvailable = True
except Exception as e:
    AndroidAvailable = False
    print("pyjnius not available:", e)

# RFCOMM SPP UUID
SPP_UUID_STR = '00001101-0000-1000-8000-00805F9B34FB'

class BTController:
    def __init__(self, status_callback=None):
        self.sock = None
        self.out_stream = None
        self.device_name = None
        self.device_addr = None
        self.status_callback = status_callback

    def _set_status(self, text):
        if self.status_callback:
            Clock.schedule_once(lambda dt: self.status_callback(text), 0)

    def request_permissions(self):
        """Запрос runtime permissions (попытка). Работает только на Android."""
        if not AndroidAvailable:
            print("No Android environment for permissions")
            return

        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            # список разрешений (Android 12+ добавь BLUETOOTH_CONNECT/SCAN)
            perms = [
                "android.permission.BLUETOOTH",
                "android.permission.BLUETOOTH_ADMIN",
                "android.permission.ACCESS_FINE_LOCATION",
                # для Android 12+ (если устройство API 31+)
                "android.permission.BLUETOOTH_CONNECT",
                "android.permission.BLUETOOTH_SCAN"
            ]
            # Попробуем вызвать requestPermissions (в jnius питон-список конвертируется)
            activity.requestPermissions(perms, 0)
            print("Requested permissions (runtime).")
        except Exception as e:
            print("request_permissions error:", e)

    def find_paired_hc06(self):
        """Ищем в списке связанных устройств устройство с именем HC-06 или похожим."""
        if not AndroidAvailable:
            self._set_status("Android API недоступен")
            return None

        try:
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            adapter = BluetoothAdapter.getDefaultAdapter()
            if not adapter:
                self._set_status("Bluetooth адаптер не найден")
                return None
            bonded = adapter.getBondedDevices()  # java.util.Set
            if bonded is None:
                self._set_status("Нет сопряжённых устройств")
                return None

            # toArray() даёт Java массив
            arr = bonded.toArray()
            for dev in arr:
                try:
                    name = dev.getName()
                    addr = dev.getAddress()
                    # ищем HC-06 по имени (включая варианты)
                    if name and ('HC-06' in name or name.upper().startswith('HC') or 'HC06' in name.replace('-','').upper()):
                        return dev
                except Exception:
                    continue
            # попробуем найти устройство с "HC" в имени
            for dev in arr:
                try:
                    name = dev.getName()
                    if name and 'HC' in name.upper():
                        return dev
                except Exception:
                    continue
            return None
        except Exception as e:
            print("find_paired_hc06 error:", e)
            self._set_status("Ошибка поиска сопряжённых")
            return None

    def connect(self):
        """Подключиться к найденному HC-06 (в отдельном потоке)."""
        def _connect_thread():
            if not AndroidAvailable:
                self._set_status("Не Android среда")
                return
            try:
                self._set_status("Поиск HC-06 среди сопряжённых...")
                dev = self.find_paired_hc06()
                if not dev:
                    self._set_status("HC-06 не найден (пара?)")
                    return

                # получение MAC/имени
                name = dev.getName()
                addr = dev.getAddress()
                self.device_name = name
                self.device_addr = addr

                BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
                adapter = BluetoothAdapter.getDefaultAdapter()

                # Создаём socket RFCOMM
                UUID = autoclass('java.util.UUID')
                spp_uuid = UUID.fromString(SPP_UUID_STR)
                socket = dev.createRfcommSocketToServiceRecord(spp_uuid)

                # Отключаем discovery (рекомендуется)
                try:
                    adapter.cancelDiscovery()
                except Exception:
                    pass

                self._set_status(f"Подключение к {name} ({addr})...")
                socket.connect()  # блокирующий

                out_stream = socket.getOutputStream()

                self.sock = socket
                self.out_stream = out_stream

                self._set_status(f"Подключено: {name} ({addr})")
            except Exception as e:
                print("connect error:", e)
                self._set_status("Ошибка подключения: " + str(e))
        threading.Thread(target=_connect_thread, daemon=True).start()

    def disconnect(self):
        try:
            if self.out_stream:
                try:
                    self.out_stream.close()
                except Exception:
                    pass
                self.out_stream = None
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
            self._set_status("Отключено")
            self.device_name = None
            self.device_addr = None
        except Exception as e:
            print("disconnect error:", e)
            self._set_status("Ошибка отключения")

    def send_ping(self):
        """Отправить PING (в отдельном потоке)."""
        def _send():
            if not self.out_stream:
                self._set_status("Не подключено")
                return
            try:
                data = "PING\n".encode('utf-8')
                self.out_stream.write(data)
                self.out_stream.flush()
                self._set_status("Отправлено: PING")
            except Exception as e:
                print("send error:", e)
                self._set_status("Ошибка при отправке: " + str(e))
        threading.Thread(target=_send, daemon=True).start()


class RootWidget(BoxLayout):
    pass

class BTTestApp(App):
    def build(self):
        Window.size = (360, 700)
        self.bt = BTController(status_callback=self.update_status)
        root = BoxLayout(orientation='vertical', padding=12, spacing=12)

        self.status_label = Label(text="Статус: Отключено", size_hint=(1, .2), halign='center')
        self.status_label.bind(size=self._update_label_wrap)

        btn_connect = Button(text="Подключить (искать HC-06)", size_hint=(1, .18))
        btn_disconnect = Button(text="Отключить", size_hint=(1, .18))
        btn_send = Button(text="Отправить PING", size_hint=(1, .18))
        btn_request_perms = Button(text="Запросить разрешения", size_hint=(1, .18))

        btn_connect.bind(on_release=lambda *a: self.bt.connect())
        btn_disconnect.bind(on_release=lambda *a: self.bt.disconnect())
        btn_send.bind(on_release=lambda *a: self.bt.send_ping())
        btn_request_perms.bind(on_release=lambda *a: self.bt.request_permissions())

        root.add_widget(self.status_label)
        root.add_widget(btn_connect)
        root.add_widget(btn_disconnect)
        root.add_widget(btn_send)
        root.add_widget(btn_request_perms)

        return root

    def _update_label_wrap(self, instance, value):
        instance.text_size = (instance.width - 20, None)

    def update_status(self, text):
        # Вызывается из BTController через Clock.schedule_once
        display = f"Статус: {text}"
        if self.bt.device_name and self.bt.device_addr:
            display += f"\nУстройство: {self.bt.device_name} ({self.bt.device_addr})"
        self.status_label.text = display

if __name__ == '__main__':
    BTTestApp().run()