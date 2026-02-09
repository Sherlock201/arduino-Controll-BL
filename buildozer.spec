[app]

title = BTTest
package.name = bttest
package.domain = org.example

source.dir = .

# точка входа
source.include_exts = py,png,jpg,kv,txt

version = 0.1

# главный питоновский файл
requirements = python3,kivy,pyjnius

# версии Android
android.api = 31
android.minapi = 21
android.ndk = 23b

# разрешения (нужны для Bluetooth)
android.permissions = INTERNET,BLUETOOTH,BLUETOOTH_ADMIN,ACCESS_FINE_LOCATION,BLUETOOTH_CONNECT,BLUETOOTH_SCAN

# иное
log_level = 2

