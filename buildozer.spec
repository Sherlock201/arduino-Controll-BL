[app]

title = BTTest
package.name = bttest
package.domain = org.example

source.dir = .
source.include_exts = py,kv,html,css,js,png,jpg

version = 0.1
requirements = python3,kivy,pyjnius,flask==2.2.5,werkzeug==2.2.3,netifaces

android.api = 27
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a
android.fullscreen = True

android.permissions = INTERNET,ACCESS_NETWORK_STATE,BLUETOOTH,BLUETOOTH_ADMIN,ACCESS_FINE_LOCATION,BLUETOOTH_CONNECT,BLUETOOTH_SCAN

# Просто добавляем атрибут в манифест
android.manifest_application_attributes = android:usesCleartextTraffic="true"

android.orientation = landscape
log_level = 2
