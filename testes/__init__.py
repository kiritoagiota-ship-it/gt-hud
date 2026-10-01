"""Testes da lógica do GT-HUD (sem tela). Rodam no GitHub antes de cada
build (o APK só sai se todos passarem) e no PC:

    python -m unittest discover -s testes -t . -v

Os testes de TELA (abrem a janela no 2º monitor e tiram fotos) ficam em
ferramentas/testes_tela/ (precisam de vídeo; não rodam no GitHub).
"""
import os

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_FILELOG", "1")
# modo PYTHON: o Kivy não sequestra o sys.stderr (senão o relatório dos
# testes some); e só avisos para cima no log
os.environ.setdefault("KIVY_LOG_MODE", "PYTHON")
os.environ.setdefault("KCFG_KIVY_LOG_LEVEL", "warning")
