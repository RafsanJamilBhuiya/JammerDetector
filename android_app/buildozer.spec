[app]
title = JammerDetector
package.name = jammerdetector
package.domain = org.jammerdetector
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json
version = 1.0.0
requirements = python3,kivy,requests,pyjnius
android.permissions = INTERNET,ACCESS_NETWORK_STATE,READ_PHONE_STATE
android.minapi = 24
android.api = 35
android.ndk_api = 24
android.accept_sdk_license = True
android.archs = arm64-v8a,armeabi-v7a
android.debug_artifact = apk
orientation = portrait
fullscreen = 0
p4a.bootstrap = sdl2

[buildozer]
log_level = 3
warn_on_root = 1
