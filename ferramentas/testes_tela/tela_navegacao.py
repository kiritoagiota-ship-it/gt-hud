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


def passo_janela(dt):
    print("[JANELA] left=%s top=%s size=%s" % (Window.left, Window.top, Window.size), flush=True)
    checar(Window.left >= 1920, "janela no segundo monitor")
    foto("1_livre")


def passo_destino(dt):
    app = App.get_running_app()
    app.escolher_destino({"nome": "Bosque dos Buritis", "endereco": "Setor Oeste, Goiania",
                          "lat": -16.6853, "lon": -49.2662})


def passo_previa(dt):
    app = App.get_running_app()
    checar(app.rota_previa is not None, "rota calculada")
    foto("2_previa")


def passo_navegar(dt):
    app = App.get_running_app()
    app.iniciar_navegacao()
    sim = app.gps._sim
    original = sim._tick
    sim._ev.cancel()
    sim._ev = Clock.schedule_interval(lambda dt: original(dt * 3), 1 / 3.0)  # 3x mais rápido


def passo_nav_foto(dt):
    app = App.get_running_app()
    checar(app.nav is not None and app.estado_nav is not None, "navegando com estado")
    foto("3_navegando")


def passo_arrastar(dt):
    mapa = App.get_running_app().sm.get_screen("mapa").mapa
    mapa._sair_do_seguir()
    mapa._arrastar(dp(160), dp(120))
    mapa._t_mexeu = time.time()
    mapa._aplicar()
    print("[DEBUG] logo apos arrastar: seguindo=%s centro=%s" % (mapa.seguindo, mapa.centro), flush=True)
    for t in (0.05, 0.5, 1.5, 3.0, 5.0):
        Clock.schedule_once(lambda dt, t=t: print("[DEBUG] +%.2fs seguindo=%s centro=%s" % (t, mapa.seguindo, mapa.centro), flush=True), t)
    foto("4_arrastado")


def passo_voltou(dt):
    mapa = App.get_running_app().sm.get_screen("mapa").mapa
    niveis = {}
    for c in mapa._desenhados:
        niveis[(c[0], c[3])] = niveis.get((c[0], c[3]), 0) + 1
    cand = sum(len(mapa.fonte.pronto(c)["rotulos"]) for c in mapa._desenhados
               if (c[0], c[3]) == mapa._nivel and mapa.fonte.pronto(c))
    print("[DEBUG] zoom=%.2f rz=%s nivel=%s desenhados=%s candidatos=%d pedidos=%d" % (
        mapa.zoom, mapa._rz, mapa._nivel, niveis, cand, len(mapa.fonte._pedidos)), flush=True)
    import math as _m
    from kivy.metrics import sp as _sp
    cx, cy, s_, ax, ay, c0, s0 = mapa._medir_quadro()
    x0, y0, x1, y1 = mapa.x + dp(8), mapa.y + dp(8), mapa.right - dp(8), mapa.top - dp(8)
    motivos = {}
    for c in mapa._desenhados:
        for r in mapa.fonte.pronto(c)["rotulos"]:
            dx, dy = (r["x"] - cx) * s_, (r["y"] - cy) * s_
            sx, sy = ax + dx * c0 - dy * s0, ay + dx * s0 + dy * c0
            if not (x0 < sx < x1 and y0 < sy < y1):
                m = "fora da tela"
            elif r["tipo"] == "rua" and r["comp"] * s_ < len(r["texto"]) * _sp(13.5) * 0.4:
                m = "trecho curto"
            elif any(a[0] < sx < a[2] and a[1] < sy < a[3] for a in mapa.areas_cobertas):
                m = "sob painel"
            else:
                m = "candidato ok (" + r["tipo"] + ")"
            motivos[m] = motivos.get(m, 0) + 1
    print("[DEBUG] motivos:", motivos, "| cobertos:", [tuple(int(v) for v in a) for a in mapa.areas_cobertas], flush=True)
    print("[DEBUG] tela", mapa.pos, mapa.size, "rotulos agendado:", mapa._ev_rotulos is not None, "t_rotulos ha %.1fs" % (time.time() - mapa._t_rotulos), flush=True)
    checar(mapa.seguindo, "voltou a seguir sozinho depois de mexer no mapa")
    checar(len(mapa._rotulos) > 0, "nomes de ruas na tela (%d)" % len(mapa._rotulos))
    foto("5_voltou")


def passo_ajustes(dt):
    App.get_running_app().abrir("config")
    Clock.schedule_once(lambda dt: foto("6_ajustes"), 0.8)


def passo_encerrar(dt):
    app = App.get_running_app()
    app.voltar()
    app.encerrar_navegacao()
    Clock.schedule_once(lambda dt: foto("7_encerrado"), 0.8)


def fim(dt):
    print("[FIM] falas:", len(FALAS), "erros:", ERROS, flush=True)
    App.get_running_app().stop()


Clock.schedule_once(passo_janela, 6)
Clock.schedule_once(passo_destino, 7)
Clock.schedule_once(passo_previa, 15)
Clock.schedule_once(passo_navegar, 16)
Clock.schedule_once(passo_nav_foto, 30)
Clock.schedule_once(passo_arrastar, 31)
Clock.schedule_once(passo_voltou, 38)
Clock.schedule_once(passo_ajustes, 40)
Clock.schedule_once(passo_encerrar, 43)
Clock.schedule_once(fim, 46)
runpy.run_path("main.py", run_name="__main__")
