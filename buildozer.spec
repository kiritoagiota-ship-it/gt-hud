[app]
title = GT-HUD
package.name = gthud
package.domain = org.kirito
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,ttf
# ferramentas/ e icone/ nao entram no APK (o icone vai pelas opcoes abaixo)
source.exclude_dirs = .github,bin,.buildozer,__pycache__,ferramentas,icone
# o workflow troca por 1.0.<numero do build> (cada APK novo e uma atualizacao)
version = 0.1.0

# sqlite3 precisa estar aqui, senao o modulo nao existe no Android
requirements = python3,kivy,pyjnius,sqlite3

# Icone e abertura: gerados por ferramentas/gerar_icones.py
icon.filename = %(source.dir)s/icone/icon.png
icon.adaptive_foreground.filename = %(source.dir)s/icone/icone_fg.png
icon.adaptive_background.filename = %(source.dir)s/icone/icone_bg.png
presplash.filename = %(source.dir)s/icone/presplash.png
android.presplash_color = #04070B

# Abre em pe; o app gira para deitada sozinho se "Tela deitada" estiver
# ligada nos Ajustes (por isso as orientacoes deitadas precisam constar aqui)
orientation = portrait, landscape, landscape-reverse
android.manifest.orientation = portrait
fullscreen = 0

android.permissions = ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,WAKE_LOCK,VIBRATE
android.api = 34
android.minapi = 24
# igual ao minapi, senao o p4a reclama de "minsdk mismatch"
android.ndk_api = 24
android.archs = arm64-v8a
android.accept_sdk_license = True

# Preenchidos automaticamente pelo workflow do GitHub Actions
android.sdk_path =
android.ndk_path =

# Usa o SDK/NDK que ja vem no runner, sem baixar nem atualizar nada
android.skip_update = True

p4a.hook = hooks.py
# mesma versao do python-for-android que o TraveteFocus usa
p4a.branch = v2026.05.09

[buildozer]
log_level = 2
warn_on_root = 0
