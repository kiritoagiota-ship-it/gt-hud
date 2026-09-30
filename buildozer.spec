[app]
title = GT-HUD
package.name = gthud
package.domain = org.kirito
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,ttf
source.exclude_dirs = .github,bin,.buildozer,__pycache__
version = 0.1.0

# sqlite3 precisa estar aqui, senao o modulo nao existe no Android
requirements = python3,kivy,plyer,pyjnius,sqlite3

orientation = portrait
fullscreen = 0

android.permissions = ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,WAKE_LOCK
android.api = 34
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True

# Preenchidos automaticamente pelo workflow do GitHub Actions
android.sdk_path =
android.ndk_path =

p4a.hook = hooks.py

[buildozer]
log_level = 2
warn_on_root = 0
