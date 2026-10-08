[app]
title = GT-HUD
package.name = gthud
package.domain = org.kirito
source.dir = .
# wav = falas do assistente (voz/, geradas por ferramentas/gerar_voz.py)
source.include_exts = py,png,jpg,kv,atlas,json,ttf,wav,db
# ferramentas/, icone/ e java/ nao entram como arquivos do app (o icone e o
# Java vao pelas opcoes proprias abaixo)
source.exclude_dirs = .github,bin,.buildozer,__pycache__,ferramentas,icone,java,testes
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
# o GT-HUD aparece no "Abrir com" quando se toca num endereço em outro app (geo:)
android.manifest.intent_filters = intent_filters.xml
fullscreen = 0

# INTERNET: mapa (tiles do OpenStreetMap), rota (Valhalla) e busca (Nominatim)
android.permissions = ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,WAKE_LOCK,VIBRATE,INTERNET,ACCESS_NETWORK_STATE,FOREGROUND_SERVICE,FOREGROUND_SERVICE_LOCATION,POST_NOTIFICATIONS,SYSTEM_ALERT_WINDOW

# Java proprio: Localizacao.java recebe o GPS e Satelites.java conta satelites
android.add_src = %(source.dir)s/java
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
