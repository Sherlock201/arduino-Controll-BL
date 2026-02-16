[app]

title = BTTest
package.name = bttest
package.domain = org.example

source.dir = .

# точка входа
source.include_exts = py,kv,html,css,js,png,jpg

version = 0.1

# главный питоновский файл
requirements = python3,kivy,pyjnius,flask

# версии Android
android.api = 31
android.minapi = 21
android.ndk = 25b

android.accept_sdk_license = True

android.arch = arm64-v8a

# разрешения (нужны для Bluetooth)
android.permissions = INTERNET,BLUETOOTH,BLUETOOTH_ADMIN,ACCESS_FINE_LOCATION,BLUETOOTH_CONNECT,BLUETOOTH_SCAN

# иное
log_level = 2

android.orientation = portrait
fullscreen = 1



