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
FOTOS = os.path.join(PASTA, "fotos_zoom")
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





def app():
    return App.get_running_app()


ZOOMS = [11.5, 13, 14.5, 15.5, 16.5, 17.5, 18.5]


def zoom_em(z, nome):
    def f(dt):
        m = app().sm.get_screen("mapa").mapa
        m._sair_do_seguir()
        m.centro = (-16.6799, -49.2550)
        m.rotacao = 0
        m.zoom = z
        m._aplicar()
        Clock.schedule_once(lambda dt: (print("[ZOOM] %s rotulos=%d sinais=%d" % (nome, len(m._rotulos), len(m._sinais)), flush=True), foto(nome)), 3.5)
    return f


t = 5
for z in ZOOMS:
    Clock.schedule_once(zoom_em(z, "z%04.1f" % z), t)
    t += 4.5
Clock.schedule_once(lambda dt: app().abrir("viagens"), t)
Clock.schedule_once(lambda dt: foto("v_viagens"), t + 1)
def detalhe(dt):
    v = app().sm.get_screen("viagens")
    itens = [w for w in v.walk() if w.__class__.__name__ == "ItemViagem"]
    if itens:
        itens[-1].dispatch("on_release")
Clock.schedule_once(detalhe, t + 2)
Clock.schedule_once(lambda dt: foto("v_detalhe"), t + 4)
Clock.schedule_once(lambda dt: app().stop(), t + 5)
runpy.run_path("main.py", run_name="__main__")
