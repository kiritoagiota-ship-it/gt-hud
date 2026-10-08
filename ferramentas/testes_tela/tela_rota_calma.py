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
    """Foto do app com o fundo do tema pintado por baixo (as telas contam com
    a cor da janela; sem isso as partes transparentes saem escuras na foto)."""
    def tirar(dt):
        from kivy.graphics import Color, Rectangle
        import tema as _t
        raiz = App.get_running_app().root
        with raiz.canvas.before:
            cor = Color(*_t.FUNDO)
            ret = Rectangle(pos=(0, 0), size=Window.size)
        caminho = os.path.join(FOTOS, nome + ".png")
        raiz.export_to_png(caminho)
        raiz.canvas.before.remove(cor)
        raiz.canvas.before.remove(ret)
        print("[FOTO]", nome, flush=True)
    Clock.schedule_once(tirar, 0)


def checar(cond, texto):
    print("[CHECA]", "OK " if cond else "FALHOU", texto, flush=True)
    if not cond:
        ERROS.append(texto)



from kivy.uix.popup import Popup  # noqa: E402
from kivy.uix.textinput import TextInput  # noqa: E402

E = {}


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


def destino(dt):
    app().ajustes["rota_preferida"] = "rapida"
    app().posicao = (-16.6799, -49.2550)
    app().escolher_destino({"nome": "Setor Sudoeste", "endereco": "", "lat": -16.7310, "lon": -49.3050})


def ver_rotas(dt):
    rs = app().rotas_previa
    print("[TESTE]", [(r.nome_perfil, round(r.total_m), r.movimentada) for r in rs], flush=True)
    rapida = rs[0]
    calmas = [r for r in rs if "tranquila" in r.nome_perfil]
    checar(len(calmas) == 1, "tem uma rota tranquila entre as opcoes (%d rotas)" % len(rs))
    checar(rapida.movimentada is not None and len(rapida.trechos) > 0, "a rapida foi medida e tem avenidas marcadas")
    if calmas:
        checar(calmas[0].movimentada < rapida.movimentada - 0.2,
               "a tranquila tem bem menos avenida: %.0f%% contra %.0f%%" % (calmas[0].movimentada * 100, rapida.movimentada * 100))
    checar("avenida" in tela().lbl_resumo.text, "previa mostra o %% de avenida: " + tela().lbl_resumo.text)
    checar(len(tela().mapa._trechos) == len(rapida.trechos), "avenidas da rota pintadas no mapa")
    foto("95_rapida_avenidas")
    if calmas:
        Clock.schedule_once(lambda dt: app().escolher_rota_previa(calmas[0]), 0.5)
        Clock.schedule_once(lambda dt: foto("96_tranquila"), 1.5)


def navegar(dt):
    app().iniciar_navegacao()
    checar("tranquila" in app().nav.rota.nome_perfil, "navegando pela tranquila")
    sim = app().gps._sim
    original = sim._tick
    sim._ev.cancel()
    sim._ev = Clock.schedule_interval(lambda dt: original(dt * 3), 1 / 3.0)


def fim(dt):
    checar(app().nav is not None and len(tela().mapa._rota) > 2, "navegacao seguindo")
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(destino, 6)
Clock.schedule_once(ver_rotas, 36)
Clock.schedule_once(navegar, 39)
Clock.schedule_once(fim, 45)
runpy.run_path("main.py", run_name="__main__")
