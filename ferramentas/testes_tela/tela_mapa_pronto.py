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




import shutil  # noqa: E402
import time  # noqa: E402

import rede  # noqa: E402

# o teste começa sem nada guardado no "celular": só vale o que vem dentro do app
shutil.rmtree(os.path.join(os.environ["APPDATA"], "gthud", "vetor", "prontos"), ignore_errors=True)

TILES_BAIXADOS = []
_baixar = rede.baixar


def baixar_contando(url, timeout=20):
    if url.endswith(".pbf"):
        TILES_BAIXADOS.append(url)
    return _baixar(url, timeout)


rede.baixar = baixar_contando
T = {}
PIOR = {"ms": 0.0, "t": None}


def app():
    return App.get_running_app()


def mapa():
    return app().sm.get_screen("mapa").mapa


def completo(m):
    """Todos os pedaços detalhados da vista estão desenhados?"""
    return bool(m._desenhados) and not m._faltando and not m._fundo_desenhado


FOTO = {}
_foto = foto


def foto(nome):
    _foto(nome)
    Clock.schedule_once(lambda dt: FOTO.__setitem__("agora", True), 0)


def vigiar(dt):
    agora = time.perf_counter()
    if PIOR["t"] is not None and T.get("medindo") and not FOTO.pop("agora", False):
        PIOR["ms"] = max(PIOR["ms"], (agora - PIOR["t"]) * 1000)
    PIOR["t"] = agora
    a = app()
    if a is None or getattr(a, "sm", None) is None:
        return
    if a.sm.current == "mapa" and "entrou" not in T:
        T["entrou"] = agora
        T["prontos_ao_entrar"] = len(mapa().fonte._prontos)
    if "entrou" in T and "completo" not in T and completo(mapa()):
        T["completo"] = agora
    alvo = T.get("esperando")
    if alvo and completo(mapa()) and mapa()._nivel[1] == alvo[0]:
        T[alvo[1]] = agora - alvo[2]
        T["esperando"] = None


def abertura(dt):
    m = mapa()
    checar("entrou" in T, "a tela do mapa abriu")
    checar(T.get("prontos_ao_entrar", 0) > 0, "o mapa já estava preparado ANTES de a tela aparecer (%d pedaços)"
           % T.get("prontos_ao_entrar", 0))
    espera = (T.get("completo", 1e9) - T.get("entrou", 0)) * 1000
    checar(espera < 400, "mapa completo %.0f ms depois de a tela aparecer" % espera)
    checar(m.fonte.lidos_do_app > 0, "veio pronto de dentro do app (%d pedaços)" % m.fonte.lidos_do_app)
    foto("m0_abertura")
    T["medindo"] = True


def ir(zoom, nome, centro=None):
    m = mapa()
    m.seguindo = False
    if centro:
        m.centro = centro
    m.zoom = zoom
    m._aplicar()
    T["esperando"] = (m._nivel[1], nome, time.perf_counter())


def passo(zoom, nome, centro=None, nivel=None, foto_nome=None):
    def ir_(dt):
        ir(zoom, nome, centro)
        if nivel is not None:
            checar(mapa()._nivel[1] == nivel, "zoom %.1f é desenhado no nível %d: %s" % (zoom, nivel, mapa()._nivel[1]))

    def ver(dt):
        checar(T.get(nome) is not None and T[nome] < 0.7,
               "zoom %.1f (%s) completo em %.0f ms" % (zoom, nome, T.get(nome, 9) * 1000))
        if foto_nome:
            foto(foto_nome)
    return ir_, ver


PASSOS = [passo(16.0, "outro_bairro", (-16.7200, -49.2950), 16),
          passo(18.4, "bem_perto", None, 17, "m1_zoom18"),
          passo(19.0, "maximo", None, 17, "m2_zoom19"),
          passo(15.0, "meio_14", None, 14, "m3_zoom15"),
          passo(15.5, "meio_16", None, 16, "m4_zoom15_5"),
          passo(12.0, "cidade", None, 12, "m5_cidade"),
          passo(17.2, "navegacao", (-16.6400, -49.2300), 17)]


def resultado(dt):
    m = mapa()
    checar(m.fonte.preparados_agora == 0, "o celular não desenhou NENHUM pedaço na hora: %d" % m.fonte.preparados_agora)
    checar(not TILES_BAIXADOS, "nada baixado da internet: %d" % len(TILES_BAIXADOS))
    print("[QUADROS] pior quadro mexendo no mapa: %.0f ms; lidos do app: %d" % (PIOR["ms"], m.fonte.lidos_do_app), flush=True)
    checar(PIOR["ms"] < 120, "sem travada longa ao pular de zoom/lugar (pior quadro %.0f ms)" % PIOR["ms"])


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_interval(vigiar, 0)
Clock.schedule_once(abertura, 7)
t = 8.0
for ir_, ver in PASSOS:
    Clock.schedule_once(ir_, t)
    Clock.schedule_once(ver, t + 1.6)
    t += 2.2
Clock.schedule_once(resultado, t)
Clock.schedule_once(fim, t + 1)
runpy.run_path("main.py", run_name="__main__")
