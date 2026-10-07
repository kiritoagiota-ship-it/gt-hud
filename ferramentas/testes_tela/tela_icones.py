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




import time  # noqa: E402

import widgets.comuns  # noqa: E402
from widgets import icones_mapa  # noqa: E402

ABERTOS = []
_escolher = widgets.comuns.escolher


def app():
    return App.get_running_app()


def mapa():
    return app().sm.get_screen("mapa").mapa


class ToqueFalso:
    def __init__(self, x, y):
        self.x, self.y, self.pos = x, y, (x, y)
        self.ud, self.time_start = {}, time.time()
        self.is_double_tap = False
        self.grab_current = None

    def grab(self, w):
        self.grab_current = w

    def ungrab(self, w):
        self.grab_current = None


def aproximar(dt):
    m = mapa()
    m.seguindo = False
    m.centro = (-16.6865, -49.2648)     # Setor Oeste: cheio de comércio
    m.zoom = 17.6
    m._aplicar()


def ver_icones(dt):
    m = mapa()
    lugares = [r for r in m._rotulos if r.info.get("tipo") == "poi"]
    icones = sorted({r.icone for r in lugares})
    print("[TESTE] %d lugares na tela, desenhos: %s" % (len(lugares), icones), flush=True)
    checar(len(lugares) >= 5, "lugares com emblema na tela: %d" % len(lugares))
    checar(len(icones) >= 3, "mais de um tipo de emblema: %s" % icones)
    checar(all(abs(r.cresce.x - 1.0) < 0.01 and r.cor.a > 0.99 for r in lugares), "os emblemas terminaram de surgir")
    foto("i0_emblemas")


def tocar(dt):
    tela = app().sm.get_screen("mapa")
    m = mapa()
    vistos = []
    real = m.ao_tocar_lugar
    m.ao_tocar_lugar = lambda lugar: (vistos.append(lugar), real(lugar))
    rot = next(r for r in m._rotulos if r.info.get("tipo") == "poi")
    sx, sy = m._local_para_tela(rot.info["x"], rot.info["y"])
    vazio = ToqueFalso(m.x + 4, m.top - 4)
    m.on_touch_down(vazio)
    m.on_touch_up(vazio)
    checar(not vistos, "tocar longe de qualquer lugar não abre nada")
    em_cima = ToqueFalso(sx + dp(3), sy - dp(2))
    m.on_touch_down(em_cima)
    m.on_touch_up(em_cima)
    checar(len(vistos) == 1 and vistos[0]["nome"] == rot.info["texto"].split(" · ")[0],
           "tocar no emblema abre o lugar: %s" % (vistos[0]["nome"] if vistos else None))
    no_nome = ToqueFalso(sx + dp(40), sy)
    m.on_touch_down(no_nome)
    m.on_touch_up(no_nome)
    checar(len(vistos) == 2, "tocar no NOME do lugar também abre")
    m.ao_tocar_lugar = real
    from kivy.uix.modalview import ModalView
    janelas = [w for w in Window.children if isinstance(w, ModalView)]
    checar(len(janelas) >= 1 and [b.text for b in janelas[0].botoes] == ["Ir para cá", "Salvar", "Fechar"],
           "cartão do lugar com Ir para cá, Salvar e Fechar")
    for w in janelas[1:]:
        w.dismiss()
    T["janela"] = janelas[0] if janelas else None
    T["lugar"] = vistos[0] if vistos else None


def ir(dt):
    janela = T.get("janela")
    if janela is None:
        return
    janela.botoes[0].dispatch("on_release")


def ver_ir(dt):
    a = app()
    checar(a.destino is not None and T["lugar"] and a.destino["nome"] == T["lugar"]["nome"],
           "\"Ir para cá\" calcula a rota até o lugar tocado: %s" % (a.destino or {}).get("nome"))
    a.cancelar_previa()


def todos_os_desenhos(dt):
    """Folha com todos os emblemas (para conferir o desenho de cada um)."""
    from kivy.graphics import Color, PopMatrix, PushMatrix, Rectangle, Scale, Translate
    from kivy.uix.widget import Widget
    import widgets.mapa as wm
    nomes = sorted(icones_mapa.NOMES)
    w = Widget(size=(dp(412), dp(300)), size_hint=(None, None))
    with w.canvas:
        Color(0.12, 0.14, 0.19, 1)
        Rectangle(pos=(0, 0), size=w.size)
    cores = list(wm.CORES_POI.values())
    for k, nome in enumerate(nomes):
        with w.canvas:
            PushMatrix()
            Translate(dp(46) + (k % 5) * dp(80), dp(250) - (k // 5) * dp(66))
            Scale(2.2, 2.2, 1)
        w.canvas.add(icones_mapa.emblema(nome, cores[k % len(cores)], (0.12, 0.14, 0.19, 1)))
        with w.canvas:
            PopMatrix()
    app().sm.get_screen("mapa").raiz.add_widget(w)
    T["folha"] = w
    Clock.schedule_once(lambda dt: w.export_to_png(os.path.join(FOTOS, "i1_todos_os_emblemas.png")), 0.3)
    checar(all(icones_mapa.qual_icone("outros", t) == e for t, e in (
        ("Posto Shell", "posto"), ("Drogaria São Paulo", "farmacia"), ("Supermercado Moreira", "mercado"),
        ("Barbearia Imagem", "salao"), ("Bar do Zé", "bar"), ("Pamonharia · restaurante", "comida"),
        ("Colégio Lyceu", "escola"), ("Nada conhecido", "ponto"))), "o desenho certo para cada tipo de nome")


T = {}


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(aproximar, 7)
Clock.schedule_once(ver_icones, 10)
Clock.schedule_once(tocar, 10.5)
Clock.schedule_once(ir, 11.5)
Clock.schedule_once(ver_ir, 13)
Clock.schedule_once(todos_os_desenhos, 14)
Clock.schedule_once(fim, 15.5)
runpy.run_path("main.py", run_name="__main__")
