"""Teste de TELA do GT-HUD (janela no 2º monitor). Rodar por
ferramentas/testes_tela/rodar_todos.py (que isola APPDATA/KIVY_HOME)."""
import os
import runpy
import sys
import time

from kivy.config import Config

Config.set("graphics", "width", "412")
Config.set("graphics", "height", "892")
Config.set("graphics", "position", "custom")
Config.set("graphics", "left", "2400")   # DISPLAY2 começa em x=1920
Config.set("graphics", "top", "60")
Config.set("input", "mouse", "mouse,disable_multitouch")

PASTA = os.path.dirname(os.path.abspath(__file__))
FOTOS = os.path.join(PASTA, "fotos")
os.makedirs(FOTOS, exist_ok=True)
for f in os.listdir(FOTOS):
    os.remove(os.path.join(FOTOS, f))

RAIZ = os.path.dirname(os.path.dirname(PASTA))  # raiz do projeto
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
sys.argv = ["main.py"]

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.metrics import dp  # noqa: E402

import voz  # noqa: E402
import widgets.mapa as wmapa  # noqa: E402

FALAS = []


def falar_falso(self, pedacos, prioridade=1, texto=None):
    import falas
    frase = texto or falas.frase([p for p in pedacos if p in falas.FALAS])
    FALAS.append(frase)
    print("[FALA]", frase, flush=True)


voz.Voz.falar = falar_falso
wmapa.VOLTA_A_SEGUIR_S = 4.0  # no teste: volta a seguir mais rápido
ERROS = []


def foto(nome):
    """Desenha o app numa imagem fora da tela (Fbo): sai sempre o quadro
    inteiro, sem a sobreposicao de monitoramento do PC por cima."""
    def tirar(dt):
        from PIL import Image
        caminho = os.path.join(FOTOS, nome + ".png")
        App.get_running_app().root.export_to_png(caminho)
        img = Image.open(caminho).convert("RGBA")
        fundo = Image.new("RGBA", img.size, (4, 7, 11, 255))  # Window.clearcolor do app
        Image.alpha_composite(fundo, img).convert("RGB").save(caminho)
        print("[FOTO]", nome, flush=True)
    Clock.schedule_once(tirar, 0)


def checar(cond, texto):
    print("[CHECA]", "OK " if cond else "FALHOU", texto, flush=True)
    if not cond:
        ERROS.append(texto)



import tema  # noqa: E402
TEXTO = {"t": "Sem sinal" + chr(10) + "12 de 63 satelites"}


def resumo_falso(self):
    return tema.VERMELHO, TEXTO["t"]


import main as _main  # noqa: E402,F401


def trocar(dt):
    App.get_running_app().__class__.resumo_gps = resumo_falso


def conferir(nome):
    def f(dt):
        tela = App.get_running_app().sm.get_screen("mapa")
        c, m = tela.status, tela.menu
        checar(c.right <= m.x, "%s: chip (%.0f..%.0f, alt %.0f) nao invade o menu (x=%.0f)"
               % (nome, c.x, c.right, c.height, m.x))
        checar(c.top <= m.top + 1 and abs(c.top - m.top) < 2, "%s: topo alinhado com o menu" % nome)
        foto(nome)
    return f


def longo(dt):
    TEXTO["t"] = "Sem sinal do GPS faz bastante tempo" + chr(10) + "12 vistos, 3 em uso agora"


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    App.get_running_app().stop()


Clock.schedule_once(trocar, 5)
Clock.schedule_once(conferir("13_chip"), 7.5)
Clock.schedule_once(longo, 8)
Clock.schedule_once(conferir("14_chip_longo"), 10.5)
Clock.schedule_once(fim, 11.5)
runpy.run_path("main.py", run_name="__main__")
