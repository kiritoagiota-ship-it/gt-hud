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


import tema  # noqa: E402
from viagem import Viagem  # noqa: E402


def inicio(dt):
    app().ajustes["tema"] = "claro"
    app().conferir_tema()
    checar(tema.modo == "claro", "tema claro aplicado")
    checar(app().root is app().sm and app().sm.parent is not None, "telas remontadas e na janela")


def boot(dt):
    app().gps.parar()                 # sem leituras: a tela inicial fica parada para a foto
    app().sm.current = "boot"
    Clock.schedule_once(lambda dt: foto("60_boot_claro"), 2.2)

    def escuro(dt):
        app().ajustes["tema"] = "escuro"
        app().conferir_tema()
        checar(tema.modo == "escuro" and app().sm.current == "boot", "trocou para escuro ficando na tela inicial")
        Clock.schedule_once(lambda dt: foto("61_boot_escuro"), 2.0)
        Clock.schedule_once(lambda dt: app().sm.get_screen("boot").anel.concluir(), 2.2)
        Clock.schedule_once(lambda dt: foto("62_boot_sinal"), 2.5)
    Clock.schedule_once(escuro, 2.6)


def destino(dt):
    app().gps.iniciar(usar_simulador=True)
    app().sm.current = "mapa"
    app().escolher_destino({"nome": "Destino teste", "endereco": "", "lat": -16.7310, "lon": -49.3050})


def navegar(dt):
    app().iniciar_navegacao()
    sim = app().gps._sim
    original = sim._tick
    sim._ev.cancel()
    sim._ev = Clock.schedule_interval(lambda dt: original(dt * 3), 1 / 3.0)


def trocar_navegando(dt):
    foto("63_nav_escuro")
    E["dist"] = app().nav.dist_feita
    nav = app().nav

    def claro(dt):
        app().ajustes["tema"] = "claro"
        app().conferir_tema()
        t = tela()
        checar(tema.modo == "claro" and app().nav is nav, "trocou de tema sem perder a navegacao")
        checar(t.estado == "navegando" and t.barra_nav.parent is not None, "tela nova ja em modo navegacao")
        checar(len(t.mapa._rota) > 1, "rota desenhada no mapa novo")
        checar(app().viagem.estado == Viagem.GRAVANDO, "a gravacao continua")
    Clock.schedule_once(claro, 0.6)


def ver_claro(dt):
    checar(app().nav.dist_feita > E["dist"] + 20, "seguiu andando depois da troca (%.0f m)" % (app().nav.dist_feita - E["dist"]))
    checar(tela().disco.velo.velocidade > 0, "velocimetro novo recebendo velocidade")
    checar(tela().col_falta.valor.text not in ("-", ""), "barra de navegacao atualizando: " + tela().col_falta.valor.text)
    foto("64_nav_claro")
    Clock.schedule_once(lambda dt: app().abrir("hud"), 0.5)
    Clock.schedule_once(lambda dt: foto("65_painel_claro"), 2.4)
    Clock.schedule_once(lambda dt: app().abrir("config"), 2.6)
    Clock.schedule_once(lambda dt: foto("66_ajustes_claro"), 3.4)


def pelo_botao(dt):
    cfg = app().sm.get_screen("config")
    checar(cfg.btn_tema.text == "Claro", "Ajustes mostra o tema: " + cfg.btn_tema.text)
    cfg.btn_tema.dispatch("on_release")       # claro -> escuro


def ver_botao(dt):
    checar(app().ajustes["tema"] == "escuro" and tema.modo == "escuro", "botao dos Ajustes trocou para escuro")
    checar(app().sm.current == "config", "continuou nos Ajustes")
    checar(app().nav is not None, "navegacao viva")
    app().voltar()
    app().sm.current = "mapa"
    Clock.schedule_once(lambda dt: checar(tela().estado == "navegando", "voltou ao mapa navegando"), 0.5)
    Clock.schedule_once(lambda dt: app().encerrar_navegacao(), 1.0)


def automatico(dt):
    import time
    app().ajustes["tema"] = "auto"
    meio_dia = time.localtime(time.mktime((2026, 10, 7, 12, 0, 0, 0, 0, -1)))
    noite = time.localtime(time.mktime((2026, 10, 7, 21, 0, 0, 0, 0, -1)))
    cedo = time.localtime(time.mktime((2026, 10, 7, 5, 30, 0, 0, 0, -1)))
    checar(tema.modo_pela_hora(-16.68, -49.25, meio_dia) == "claro", "meio-dia: claro")
    checar(tema.modo_pela_hora(-16.68, -49.25, noite) == "escuro", "21h: escuro")
    checar(tema.modo_pela_hora(-16.68, -49.25, cedo) == "escuro", "5h30: ainda escuro")
    app().conferir_tema()
    checar(tema.modo == app().tema_desejado(), "automatico aplicou o tema da hora: " + tema.modo)


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(inicio, 5)
Clock.schedule_once(boot, 6)
Clock.schedule_once(destino, 12.5)
Clock.schedule_once(navegar, 22)
Clock.schedule_once(trocar_navegando, 27)
Clock.schedule_once(ver_claro, 32)
Clock.schedule_once(pelo_botao, 36.5)
Clock.schedule_once(ver_botao, 37.5)
Clock.schedule_once(automatico, 40)
Clock.schedule_once(fim, 42)
runpy.run_path("main.py", run_name="__main__")
