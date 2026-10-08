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



from kivy.uix.popup import Popup  # noqa: E402
from kivy.uix.textinput import TextInput  # noqa: E402

E = {}


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


def janelas():
    return [w for w in Window.children if isinstance(w, Popup)]


def colar(texto):
    b = app().sm.get_screen("busca")
    b.campo.text = texto
    b._buscar()


def abrir(dt):
    app().salvos = []
    app().abrir("busca")
    achado = busca.buscar("bosque dos buritis")[0]
    E["nome"] = achado["nome"]
    Clock.schedule_once(lambda dt: colar("%.6f, %.6f" % (achado["lat"], achado["lon"])), 0.6)


def escolher_coordenada(dt):
    b = app().sm.get_screen("busca")
    checar(len(b.lista.children) == 1, "coordenada colada virou 1 resultado: " + b.lbl_status.text)
    b.lista.children[0].dispatch("on_release")

    def conferir(dt):
        pop = janelas()
        checar(len(pop) == 1, "perguntou o nome do lugar colado")
        if not pop:
            return
        checar(pop[0].campo.text == E["nome"], "ja sugeriu o lugar conhecido ali: %r" % pop[0].campo.text)
        foto("40_nome_sugerido")
        Clock.schedule_once(lambda dt: pop[0].confirmar(), 0.3)
    Clock.schedule_once(conferir, 0.6)


def ver_coordenada(dt):
    checar(bool(app().salvos) and app().salvos[0]["nome"] == E["nome"], "salvou com o nome: %s" % app().salvos[:1])
    checar(app().destino is not None and app().destino["nome"] == E["nome"], "destino com o nome: %s" % (app().destino or {}).get("nome"))
    checar(not janelas(), "janela fechou")
    app().abrir("busca")
    Clock.schedule_once(lambda dt: colar("9MJH+9W Goiânia"), 0.6)


def escolher_codigo(dt):
    b = app().sm.get_screen("busca")
    b.lista.children[0].dispatch("on_release")

    def conferir(dt):
        pop = janelas()
        checar(len(pop) == 1 and pop[0].campo.text == "", "Plus Code sem lugar conhecido: pergunta com o campo vazio")
        if not pop:
            return
        antes = len(app().salvos)
        pop[0].confirmar()
        checar(len(app().salvos) == antes and len(janelas()) == 1, "sem nome nao salva nem fecha")
        pop[0].campo.text = "Barbearia Imagem"
        foto("41_nome_digitado")
        Clock.schedule_once(lambda dt: pop[0].confirmar(), 0.3)
    Clock.schedule_once(conferir, 0.6)


def ver_codigo(dt):
    checar(app().salvos[0]["nome"] == "Barbearia Imagem", "Plus Code salvo com o nome digitado")
    checar(app().destino["nome"] == "Barbearia Imagem" and "sem_nome" not in app().destino, "destino: %s" % app().destino)


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


import busca  # noqa: E402

Clock.schedule_once(abrir, 6)
Clock.schedule_once(escolher_coordenada, 9)
Clock.schedule_once(ver_coordenada, 11)
Clock.schedule_once(escolher_codigo, 14)
Clock.schedule_once(ver_codigo, 16)
Clock.schedule_once(fim, 18)
runpy.run_path("main.py", run_name="__main__")
