[app]
title = JammerDetector
package.name = jammerdetector
package.domain = org.jammerdetector
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json
version = 1.0.0
requirements = python3,kivy,requests,pyjnius
android.permissions = INTERNET,ACCESS_NETWORK_STATE,READ_PHONE_STATE
android.minapi = 23
android.api = 35
android.accept_sdk_license = True
android.archs = arm64-v8a,armeabi-v7a
orientation = portrait
fullscreen = 0

[buildozer]
log_level = 2
warn_on_root = 1
