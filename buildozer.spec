[app]

title = BTTest
package.name = bttest
package.domain = org.example

source.dir = .

# точка входа
source.include_exts = py,kv,html,css,js,png,jpg

version = 0.1

# главный питоновский файл
#requirements = python3,kivy,pyjnius,flask==2.0.3,werkzeug==2.0.3,markupsafe==2.0.1
requirements = python3,kivy,pyjnius,flask==2.2.5,werkzeug==2.2.3,netifaces

android.resources = res

android.presplash_color = #f5f7fb

# версии Android
android.api = 28
android.minapi = 21
android.ndk = 25b

android.accept_sdk_license = True

android.archs = arm64-v8a
android.fullscreen = True

android.gradle_dependencies = androidx.core:core:1.6.0
android.enable_androidx = True

# разрешения (нужны для Bluetooth)
android.permissions = INTERNET,ACCESS_NETWORK_STATE,BLUETOOTH,BLUETOOTH_ADMIN,ACCESS_FINE_LOCATION,BLUETOOTH_CONNECT,BLUETOOTH_SCAN

# android.manifest_application_attributes = android:usesCleartextTraffic="true"
#android.manifest_application_attributes = android:networkSecurityConfig="@xml/network_security_config"

android.network_security_config = res/xml/network_security_config.xml

android.manifest_application_attributes = android:usesCleartextTraffic="true"
#android.gradle_manifest = manifest/AndroidManifest.xml

# иное
log_level = 2

android.orientation = landscape












