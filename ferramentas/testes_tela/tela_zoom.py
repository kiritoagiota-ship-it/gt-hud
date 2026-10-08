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
import caminhos  # noqa: E402,F401  (as pastas do código no caminho de busca)
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





import psutil  # noqa: E402

PROC = psutil.Process()
E = {"pico": 0, "passos": 0}


def app():
    return App.get_running_app()


def mem():
    return PROC.memory_info().rss / 1e6


def zoom_louco(dt):
    """Pinça de 11 até 19 e de volta, várias vezes, em lugares diferentes."""
    m = app().sm.get_screen("mapa").mapa
    k = E["passos"]
    alvo = 11 + (k % 32) / 4.0 if (k // 32) % 2 == 0 else 19 - (k % 32) / 4.0
    m._sair_do_seguir()
    m._zoom_no_ponto(alvo, m.center_x + (k % 7) * 20, m.center_y - (k % 5) * 30)
    m._arrastar(15 * ((k % 3) - 1), 15)
    m._aplicar()
    E["passos"] += 1
    E["pico"] = max(E["pico"], mem())
    if E["passos"] % 32 == 0:
        print("[MEM] passo %d zoom %.1f: %.0f MB (pico %.0f), preparados %d, decodificados %d" % (
            E["passos"], m.zoom, mem(), E["pico"], len(m.fonte._prontos), len(m.fonte._decodificados)), flush=True)
    if E["passos"] >= 32 * 8:
        checar(True, "zoom de 11 a 19 varias vezes sem fechar")
        print("[FIM] erros:", ERROS, flush=True)
        app().stop()
        return False


Clock.schedule_once(lambda dt: print("[MEM] inicio: %.0f MB" % mem(), flush=True), 5)
Clock.schedule_once(lambda dt: Clock.schedule_interval(zoom_louco, 0.12), 6)
runpy.run_path("main.py", run_name="__main__")
