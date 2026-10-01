"""Teste de TELA do GT-HUD (janela no 2º monitor). Rodar por
ferramentas/testes_tela/rodar_todos.py (que isola APPDATA/KIVY_HOME)."""
import cProfile
import io
import os
import pstats
import runpy
import shutil
import sys
import time

from kivy.config import Config

Config.set("graphics", "width", "412")
Config.set("graphics", "height", "892")
Config.set("graphics", "position", "custom")
Config.set("graphics", "left", "2400")
Config.set("graphics", "top", "60")
Config.set("graphics", "maxfps", "60")
Config.set("input", "mouse", "mouse,disable_multitouch")

PASTA = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(PASTA))  # raiz do projeto
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
sys.argv = ["main.py"]
LIMPAR_CACHE = "--frio" in sys.argv[1:] or os.environ.get("FRIO") == "1"

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402

import voz  # noqa: E402
import mapa_vetor  # noqa: E402
from kivy.graphics.tesselator import Tesselator as _T  # noqa: E402
if os.environ.get("EXPERIMENTO") == "1":
    sys.setswitchinterval(0.001)
    mapa_vetor.TRABALHADORES = 1
MAIOR_TESS = {"ms": 0.0, "n": 0}
import gc  # noqa: E402
import threading  # noqa: E402
GC = {"t0": 0.0, "lista": []}


def gc_cb(fase, info):
    if fase == "start":
        GC["t0"] = time.perf_counter()
    else:
        GC["lista"].append((info["generation"], (time.perf_counter() - GC["t0"]) * 1000,
                            threading.current_thread() is threading.main_thread()))


pass  # gc.callbacks.append(gc_cb)
_orig_area_prep = mapa_vetor.preparar


def prep_medido(*a, **k):
    t0 = time.perf_counter()
    r = _orig_area_prep(*a, **k)
    MAIOR_TESS["n"] += 1
    MAIOR_TESS["ms"] = max(MAIOR_TESS["ms"], (time.perf_counter() - t0) * 1000)
    return r


mapa_vetor.preparar = prep_medido
import widgets.mapa as wm  # noqa: E402

GASTO = {}          # nome -> ms neste quadro
TRAVADAS = []       # (fase, ms do quadro, {nome: ms}, trabalhadores ocupados)
OCUPADOS = {"n": 0}


def cronometrar(classe, nome):
    original = getattr(classe, nome)

    def embrulho(*a, **k):
        t0 = time.perf_counter()
        try:
            return original(*a, **k)
        finally:
            GASTO[nome] = GASTO.get(nome, 0.0) + (time.perf_counter() - t0) * 1000
    embrulho.__name__ = embrulho.__qualname__ = nome
    setattr(classe, nome, embrulho)


for n in ("_desenhar_tile", "_escolher_rotulos", "_refazer_linhas", "_ajustar_larguras",
          "_apagar_tile", "_atualizar_tiles", "_mover_rotulos", "_desenhar_tela"):
    cronometrar(wm.MapaHUD, n)
cronometrar(wm.MapaHUD, "_textura")
_prep = mapa_vetor.FonteVetorial._preparar


def prep_contado(self, chave):
    OCUPADOS["n"] += 1
    try:
        return _prep(self, chave)
    finally:
        OCUPADOS["n"] -= 1


mapa_vetor.FonteVetorial._preparar = prep_contado

voz.Voz.falar = lambda self, p, prioridade=1, texto=None: None

FASE = {"nome": "inicio"}
DADOS = {}          # fase -> lista de (dt_ms, mov_seta_px)
ULT = {"t": None, "seta": None}
PERFIL = cProfile.Profile()


def medir(dt):
    agora = time.perf_counter()
    app = App.get_running_app()
    if app is None or ULT["t"] is None:
        ULT["t"] = agora
        return
    quadro = (agora - ULT["t"]) * 1000.0
    ULT["t"] = agora
    mov = 0.0
    try:
        mapa = app.sm.get_screen("mapa").mapa
        pos_seta = getattr(mapa, "_vista", None) or (mapa.eu[:2] if mapa.eu else None)
        if pos_seta:
            x, y = mapa._para_tela(pos_seta[0], pos_seta[1])
            # posição da seta relativa ao MUNDO visto: soma o deslocamento
            # da seta na tela + o do mapa por baixo dela
            cx, cy = mapa._local(*mapa.centro)
            s = mapa._escala_tela()
            pos = (x, y, cx * s, cy * s)
            if ULT["seta"] is not None:
                a = ULT["seta"]
                mov = ((pos[0] - a[0]) ** 2 + (pos[1] - a[1]) ** 2) ** 0.5 \
                    + ((pos[2] - a[2]) ** 2 + (pos[3] - a[3]) ** 2) ** 0.5
            ULT["seta"] = pos
    except Exception:
        pass
    DADOS.setdefault(FASE["nome"], []).append((quadro, mov))
    if quadro > 30:
        TRAVADAS.append((FASE["nome"], quadro, dict(GASTO), OCUPADOS["n"]))
    GASTO.clear()


def fase(nome):
    def f(dt):
        FASE["nome"] = nome
        ULT["seta"] = None
        print("[FASE]", nome, flush=True)
    return f


def iniciar_nav(dt):
    app = App.get_running_app()
    app.escolher_destino({"nome": "Bosque dos Buritis", "endereco": "", "lat": -16.6853, "lon": -49.2662})


def comecar(dt):
    app = App.get_running_app()
    if app.rota_previa is None:
        print("[ERRO] sem rota", flush=True)
        return
    app.iniciar_navegacao()
    PERFIL.enable()


def parar_perfil(dt):
    PERFIL.disable()


def trocar_tela(dt):
    app = App.get_running_app()
    app.abrir("config")
    Clock.schedule_once(lambda dt: app.voltar(), 1.5)


def zoom(dt):
    mapa = App.get_running_app().sm.get_screen("mapa").mapa
    mapa.mudar_zoom(-2)
    Clock.schedule_once(lambda dt: mapa.mudar_zoom(2), 1.5)


def resumo(dt):
    print("\n=== FLUIDEZ (PC) ===", flush=True)
    for nome, v in DADOS.items():
        if len(v) < 5:
            continue
        qs = sorted(q for q, _ in v)
        movs = [m for _, m in v]
        n = len(qs)
        p50, p95, mx = qs[n // 2], qs[int(n * 0.95)], qs[-1]
        lentos = sum(1 for q in qs if q > 25)
        parados = sum(1 for m in movs if m < 0.05)
        media_mov = sum(movs) / n
        maior_mov = max(movs)
        print("%-22s quadros=%4d  p50=%5.1fms p95=%5.1fms max=%6.1fms  >25ms=%3d  "
              "seta: media %.2f px/q, maior %.1f px/q, parada em %d%% dos quadros"
              % (nome, n, p50, p95, mx, lentos, media_mov, maior_mov, 100 * parados // n), flush=True)
    for g in (0, 1, 2):
        v = [ms for gg, ms, _ in GC["lista"] if gg == g]
        if v:
            print("coletor de lixo geracao %d: %d vezes, total %.0f ms, maior %.1f ms" % (g, len(v), sum(v), max(v)))
    print("tiles preparados: %d, o mais demorado: %.0f ms" % (MAIOR_TESS["n"], MAIOR_TESS["ms"]))
    print("--- quadros > 30 ms (gasto do quadro ANTERIOR por funcao) ---")
    for f, q, g, oc in TRAVADAS:
        partes = ", ".join("%s %.0f" % (k, v) for k, v in sorted(g.items(), key=lambda kv: -kv[1]) if v >= 1)
        print("%-14s %6.0f ms | trabalhadores ocupados: %d | %s" % (f, q, oc, partes), flush=True)
    App.get_running_app().stop()


if LIMPAR_CACHE:
    pasta_vetor = os.path.join(PASTA, "appdata_frio")
    shutil.rmtree(pasta_vetor, ignore_errors=True)

Clock.schedule_interval(medir, 0)
Clock.schedule_once(fase("livre_parado"), 6)
Clock.schedule_once(iniciar_nav, 9)
Clock.schedule_once(fase("previa"), 9.2)
Clock.schedule_once(comecar, 16)
Clock.schedule_once(fase("navegando"), 16.5)
Clock.schedule_once(parar_perfil, 31)
Clock.schedule_once(fase("troca_de_tela"), 31)
Clock.schedule_once(trocar_tela, 31.2)
Clock.schedule_once(fase("navegando_2"), 34.5)
Clock.schedule_once(fase("zoom"), 40)
Clock.schedule_once(zoom, 40.2)
Clock.schedule_once(fase("navegando_3"), 44)
Clock.schedule_once(resumo, 52)
runpy.run_path("main.py", run_name="__main__")
