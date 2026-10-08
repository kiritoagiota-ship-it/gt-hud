"""Teste de TELA do GT-HUD (janela no 2º monitor). Rodar por
ferramentas/testes_tela/rodar_todos.py (que isola APPDATA/KIVY_HOME)."""
import os
import runpy
import sys
import time

from kivy.config import Config

Config.set("graphics", "width", "892")
Config.set("graphics", "height", "412")
Config.set("graphics", "position", "custom")
Config.set("graphics", "left", "2400")   # DISPLAY2 começa em x=1920
Config.set("graphics", "top", "60")
Config.set("input", "mouse", "mouse,disable_multitouch")

PASTA = os.path.dirname(os.path.abspath(__file__))
FOTOS = os.path.join(PASTA, "fotos_deitada")
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


SEQ = []


def passo(t, f):
    SEQ.append((t, f))


passo(6, lambda: foto("a_mapa_livre"))
passo(7, lambda: app().abrir("busca"))
passo(8, lambda: foto("b_busca"))
def buscar():
    b = app().sm.get_screen("busca"); b.campo.text = "farmacia"; b._buscar()
passo(8.5, buscar)
passo(11, lambda: foto("c_busca_result"))
passo(12, lambda: app().escolher_destino({"nome": "Bosque dos Buritis - um nome bem comprido de lugar", "endereco": "",
                                          "lat": -16.6853, "lon": -49.2662}))
passo(22, lambda: foto("d_previa"))
def nav():
    app().iniciar_navegacao()
passo(23, nav)
passo(33, lambda: foto("e_navegando"))
passo(34, lambda: app().abrir("hud"))
passo(35, lambda: foto("f_painel"))
passo(36, lambda: app().voltar())
passo(37, lambda: app().encerrar_navegacao())
passo(38, lambda: app().abrir("viagens"))
passo(39, lambda: foto("g_viagens"))
passo(40, lambda: app().voltar())
passo(41, lambda: app().abrir("config"))
passo(42, lambda: foto("h_ajustes"))
def ajustes_meio():
    c = app().sm.get_screen("config")
    rol = [w for w in c.walk() if w.__class__.__name__ == "ScrollView"][0]
    rol.scroll_y = 0.45
passo(42.5, ajustes_meio)
passo(43.5, lambda: foto("i_ajustes_meio"))
def ajustes_fim():
    c = app().sm.get_screen("config")
    rol = [w for w in c.walk() if w.__class__.__name__ == "ScrollView"][0]
    rol.scroll_y = 0
passo(44, ajustes_fim)
passo(45, lambda: foto("j_ajustes_fim"))
passo(46, lambda: app().voltar())
passo(46.5, lambda: app().sm.get_screen("mapa")._ao_segurar(-16.70, -49.27))
passo(47.5, lambda: foto("k_marcado"))
passo(48.5, lambda: app().stop())
for t, f in SEQ:
    Clock.schedule_once(lambda dt, f=f: f(), t)
runpy.run_path("main.py", run_name="__main__")
