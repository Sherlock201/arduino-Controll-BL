[app]
title = BTTest
package.name = bttest
package.domain = org.example

source.dir = .
source.include_exts = py,kv,html,css,js,png,jpg

version = 0.1

requirements = python3,kivy,pyjnius,flask==2.2.5,werkzeug==2.2.3,netifaces

android.presplash_color = #f5f7fb

android.api = 31
android.minapi = 21
android.ndk = 25b

android.accept_sdk_license = True

android.archs = arm64-v8a
android.fullscreen = True

# ВАЖНО: Добавь эту строку
android.resources = res

# Конфиг безопасности сети
android.network_security_config = network_security_config

android.gradle_dependencies = androidx.core:core:1.6.0
android.enable_androidx = True

android.permissions = INTERNET,ACCESS_NETWORK_STATE,BLUETOOTH,BLUETOOTH_ADMIN,ACCESS_FINE_LOCATION,BLUETOOTH_CONNECT,BLUETOOTH_SCAN

# Также добавь это для явного разрешения cleartext
android.gradle_manifest_application_attributes = android:usesCleartextTraffic="true"
android.gradle_manifest = android/AndroidManifest.xml

android.orientation = landscape
log_level = 2
