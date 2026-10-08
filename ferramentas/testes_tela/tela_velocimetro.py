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



AMOSTRAS = []


def gravar_velo(dt):
    app = App.get_running_app()
    tela = app.sm.get_screen(app.sm.current)
    velo = getattr(tela, "velo", None) or getattr(getattr(tela, "disco", None), "velo", None)
    if velo is not None:
        AMOSTRAS.append((app.sm.current, velo.velocidade, velo._mostrada))


def abrir_painel(dt):
    App.get_running_app().abrir("hud")


def fotos_e_fim(dt):
    foto("15_painel")
    def fim(dt):
        mapa_q = [a for a in AMOSTRAS if a[0] == "mapa"]
        hud_q = [a for a in AMOSTRAS if a[0] == "hud"]
        for nome, q in (("mapa", mapa_q), ("painel", hud_q)):
            mostrados = [round(m, 1) for _, _, m in q]
            saltos = [abs(b - a) for a, b in zip(mostrados, mostrados[1:])]
            checar(len(set(mostrados)) > 20, "%s: velocimetro passa por %d valores (suave)" % (nome, len(set(mostrados))))
            checar(max(saltos or [0]) < 6, "%s: maior salto por quadro %.1f km/h" % (nome, max(saltos or [0])))
        velo = App.get_running_app().sm.get_screen("hud").velo
        import time as _t
        t0 = _t.perf_counter()
        for k in range(200):
            velo._mostrada = k % 50
            velo._colorir()
        print("[CUSTO] _colorir: %.3f ms" % ((_t.perf_counter() - t0) * 1000 / 200), flush=True)
        t0 = _t.perf_counter()
        for k in range(50):
            velo._desenhar()
        print("[CUSTO] _desenhar (montar anel): %.3f ms" % ((_t.perf_counter() - t0) * 1000 / 50), flush=True)
        print("[FIM] erros:", ERROS, flush=True)
        App.get_running_app().stop()
    Clock.schedule_once(fim, 1)


Clock.schedule_interval(gravar_velo, 0)
Clock.schedule_once(abrir_painel, 14)
Clock.schedule_once(fotos_e_fim, 22)
runpy.run_path("main.py", run_name="__main__")
