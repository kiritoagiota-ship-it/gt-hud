"""Teste de TELA do GT-HUD (janela no 2º monitor): o "Testar o Umbra" dos Ajustes passa por todas
as peças, uma de cada vez, e termina dizendo que todas passaram. Rodar por rodar_todos.py."""
import os
import runpy
import sys

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
RAIZ = os.path.dirname(os.path.dirname(PASTA))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
import caminhos  # noqa: E402,F401
sys.argv = ["main.py"]

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402

import diagnostico  # noqa: E402
import umbra_teste  # noqa: E402

ERROS = []
PASSARAM = []
_print = diagnostico._Copia.write


def checar(cond, texto):
    print("[CHECA]", "OK " if cond else "FALHOU", texto, flush=True)
    if not cond:
        ERROS.append(texto)


def app():
    return App.get_running_app()


def comeco(dt):
    a = app()
    a.umbra.microfone = True
    a.testar_umbra()


def foto(nome):
    Window.screenshot(name=os.path.join(FOTOS, nome + ".png"))


def olhar(dt):
    t = getattr(app(), "_teste_umbra", None)
    if t is not None and t.ativo and 0 <= t.i < len(umbra_teste.PASSOS):
        nome = umbra_teste.PASSOS[t.i][0]
        if nome not in PASSARAM:
            PASSARAM.append(nome)
            if nome in ("imagem", "desenho_minimo", "so_cabeca", "completo"):
                Clock.schedule_once(lambda d: foto("t_" + nome), 1.2)
    return True


def fim(dt):
    t = app()._teste_umbra
    checar(not t.ativo, "o teste terminou")
    checar(PASSARAM == [p[0] for p in umbra_teste.PASSOS], "passou por todas as peças, em ordem: %s" % PASSARAM)
    checar(diagnostico.etapa_que_derrubou() is None, "nenhuma queda anotada")
    r = app().sm.get_screen("mapa").rosto_umbra
    checar(not r.em_teste and r.fonte_propria is None and r.definicoes == "", "o rosto voltou ao normal depois do teste")
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(comeco, 7)
Clock.schedule_interval(olhar, 0.2)
Clock.schedule_once(fim, 7 + 1.5 + sum(p[2] for p in umbra_teste.PASSOS) + 3)
runpy.run_path("main.py", run_name="__main__")
