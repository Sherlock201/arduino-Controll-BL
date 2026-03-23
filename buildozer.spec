[app]
title = BTTest
package.name = bttest
package.domain = org.example
source.dir = .
source.include_exts = py,kv,html,css,js,png,jpg
version = 0.1
requirements = python3,kivy,pyjnius,netifaces

# ПРАВКА 1: Указываем папку с ресурсами (без res в пути, buildozer сам подцепит подпапки)
android.add_res_dir = res

# ПРАВКА 2: Атрибуты через ЗАПЯТУЮ
android.manifest.application_attributes = android:networkSecurityConfig="@xml/network_security_config", android:usesCleartextTraffic="true"

android.presplash_color = #f5f7fb
android.api = 31
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a
android.fullscreen = True
android.gradle_dependencies = androidx.core:core:1.6.0
android.enable_androidx = True
android.permissions = INTERNET,ACCESS_NETWORK_STATE,BLUETOOTH,BLUETOOTH_ADMIN,ACCESS_FINE_LOCATION,BLUETOOTH_CONNECT,BLUETOOTH_SCAN
android.orientation = landscape
log_level = 2

[buildozer]
log_level = 2
warn_on_root = 1
