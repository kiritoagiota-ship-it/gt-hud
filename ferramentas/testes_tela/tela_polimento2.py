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




import fluxo  # noqa: E402
import transito  # noqa: E402
import widgets.comuns as comuns  # noqa: E402

M = 1.0 / 111320.0


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


def tile_falso(self, chave, x, y):
    """Trechos como os da TomTom: longos com curva, e um toquinho de 10 m (que antes virava um quadrado)."""
    lat, lon = app().posicao
    segmentos = [([(lat + 150 * M - k * 30 * M, lon - 40 * M + k * 6 * M) for k in range(11)], 0),
                 ([(lat + 150 * M - k * 30 * M, lon - 25 * M + k * 6 * M) for k in range(6)]
                  + [(lat - 20 * M, lon + 25 * M), (lat - 60 * M, lon + 20 * M)], 3),
                 ([(lat - 60 * M - k * 30 * M, lon + 10 * M + k * 6 * M) for k in range(8)], 1),
                 ([(lat - 62 * M, lon + 22 * M), (lat - 70 * M, lon + 22 * M)], 3)]
    segmentos = [(p, n) for p, n in segmentos if fluxo._comprimento_m(p) >= fluxo.TRECHO_MIN_M]
    with self._trava:
        self._tiles[(x, y)] = (__import__("time").monotonic(), segmentos)
    return segmentos


fluxo.Fluxo.buscar_tile = tile_falso
transito.da_cidade = lambda chave, agora=None, baixar=None: []


def ligar(dt):
    a = app()
    a.ajustes["tomtom"] = "chave-de-mentira-para-o-teste"
    m = tela().mapa
    m.seguindo = False
    m.zoom = 18.6
    m._aplicar()
    a._fluxo_tiles = None
    a.atualizar_fluxo()


def ver_fluxo(dt):
    m = tela().mapa
    checar(len(m._fluxo) == 3, "o toquinho de 10 m ficou de fora: %d trechos" % len(m._fluxo))
    checar(m._fluxo_rz == (18.5, True), "largura feita para o zoom de agora: %s" % (m._fluxo_rz,))
    import tema   # (o tema de agora depende dos ajustes que sobraram do teste anterior)
    checar(tema.TEXTOS["monarca"]["para_onde"] == "Para onde vamos?"
           and tela().busca.lbl.text == tema.texto("para_onde", "Para onde?"),
           "texto da busca: %s" % tela().busca.lbl.text)
    Window.screenshot(name=os.path.join(FOTOS, "j0_fluxo_de_perto.png"))


def popup(dt):
    T["janela"] = comuns.escolher("Goodgyndelicias", [("Ir para cá", lambda: None), ("Salvar", lambda: None), ("Fechar", None)],
                                  "Restaurante ou lanchonete\nA 1,98 km daqui, em linha reta.")
    Clock.schedule_once(lambda dt: Window.screenshot(name=os.path.join(FOTOS, "j1_janela_abrindo.png")), 0.08)
    Clock.schedule_once(lambda dt: Window.screenshot(name=os.path.join(FOTOS, "j2_janela_aberta.png")), 0.6)


def ver_popup(dt):
    j = T["janela"]
    checar(j.opacity > 0.99, "janela terminou de aparecer")
    j.dismiss()


T = {}


def fim(dt):
    app().ajustes["tomtom"] = ""
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(ligar, 7)
Clock.schedule_once(ver_fluxo, 9.5)
Clock.schedule_once(popup, 10.5)
Clock.schedule_once(ver_popup, 12)
Clock.schedule_once(fim, 13)
runpy.run_path("main.py", run_name="__main__")
