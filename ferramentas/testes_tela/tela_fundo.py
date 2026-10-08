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




def app():
    return App.get_running_app()


def destino(dt):
    app().escolher_destino({"nome": "Bosque dos Buritis", "endereco": "", "lat": -16.6853, "lon": -49.2662})


def navegar(dt):
    app().iniciar_navegacao()


def foto_nav(dt):
    t = app().sm.get_screen("mapa")
    checar(t.btn_rotas.parent is not None, "botao Rotas no mapa")
    checar(t.btn_rotas.height >= 50 and t.btn_mais.height >= 50, "botoes grandes (%d dp)" % t.btn_mais.height)
    foto("30_nav_botoes")


def minimizar(dt):
    app().on_pause()
    checar(app().fundo.minimizado, "minimizado com rota: segundo plano ligado")
    checar(app().fundo._thread is not None and app().fundo._thread.is_alive(), "thread de segundo plano rodando")


def voltar(dt):
    app().on_resume()
    checar(not app().fundo.minimizado, "voltou: segundo plano desligado")
    checar(app().fundo._thread is None, "thread parada")
    foto("31_voltou")


def ajustes(dt):
    app().abrir("config")
    def rolar(dt):
        c = app().sm.get_screen("config")
        rol = [w for w in c.walk() if w.__class__.__name__ == "ScrollView"][0]
        rol.scroll_y = 0.62
        Clock.schedule_once(lambda dt: foto("32_ajustes_fundo"), 0.5)
    Clock.schedule_once(rolar, 0.6)


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(destino, 6)
Clock.schedule_once(navegar, 14)
Clock.schedule_once(foto_nav, 18)
Clock.schedule_once(minimizar, 19)
Clock.schedule_once(voltar, 23)
Clock.schedule_once(ajustes, 25)
Clock.schedule_once(fim, 28)
runpy.run_path("main.py", run_name="__main__")
