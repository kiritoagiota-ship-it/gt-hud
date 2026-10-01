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





def app():
    return App.get_running_app()


def preparar(dt):
    a = app()
    a.salvos, a.recentes = [], []
    a.salvar_lugar("Barbearia do amigo", -16.6190, -49.3202)
    a.salvar_lugar("Casa da vó", -16.7000, -49.2700)
    a._guardar_recente({"nome": "Barbearia do amigo", "endereco": "", "lat": -16.6190, "lon": -49.3202})
    a._guardar_recente({"nome": "Padaria", "endereco": "", "lat": -16.6900, "lon": -49.2600})
    a.abrir("busca")


def conferir_lista(dt):
    b = app().sm.get_screen("busca")
    checar(len(b.lista.children) == 3, "lista sem repetir o salvo nos recentes (%d itens)" % len(b.lista.children))
    foto("40_salvos_recentes")
    botoes = [w for w in b.lista.walk() if getattr(w, "text", "") == "Apagar"]
    checar(len(botoes) == 3, "todos com Apagar (%d)" % len(botoes))
    # apaga a "Barbearia do amigo": o botão da linha que tem esse nome
    for linha in b.lista.children:
        textos = [getattr(w, "text", "") for w in linha.walk()]
        if "Barbearia do amigo" in textos:
            [w for w in linha.walk() if getattr(w, "text", "") == "Apagar"][0].dispatch("on_release")


def conferir_apagado(dt):
    a = app()
    b = a.sm.get_screen("busca")
    nomes = [s["nome"] for s in a.salvos] + [r["nome"] for r in a.recentes]
    checar("Barbearia do amigo" not in nomes, "apagou dos salvos E dos recentes: %s" % nomes)
    checar(len(b.lista.children) == 2, "lista atualizada (%d itens)" % len(b.lista.children))
    foto("41_depois_de_apagar")


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(preparar, 5)
Clock.schedule_once(conferir_lista, 6.5)
Clock.schedule_once(conferir_apagado, 7.5)
Clock.schedule_once(fim, 8.5)
runpy.run_path("main.py", run_name="__main__")
