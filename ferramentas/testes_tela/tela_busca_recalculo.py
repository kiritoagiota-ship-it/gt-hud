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



def passo_busca(dt):
    app = App.get_running_app()
    app.abrir("busca")
    tela = app.sm.get_screen("busca")
    tela.campo.text = "Bosque dos Buritis"
    tela._buscar()


def passo_busca_foto(dt):
    tela = App.get_running_app().sm.get_screen("busca")
    checar(len(tela.lista.children) > 0, "busca achou resultados: " + tela.lbl_status.text)
    foto("8_busca")


def passo_longe(dt):
    App.get_running_app().escolher_destino({"nome": "Avenida Paulista", "endereco": "Sao Paulo",
                                             "lat": -23.5614, "lon": -46.6559})


def passo_longe_foto(dt):
    tela = App.get_running_app().sm.get_screen("mapa")
    checar("Fora de Goi" in tela.lbl_resumo.text, "destino fora de Goiania: " + tela.lbl_resumo.text)
    checar(tela.btn_iniciar.disabled, "Iniciar desligado sem rota")
    foto("9_longe")


def passo_destino(dt):
    app = App.get_running_app()
    app.cancelar_previa()
    app.escolher_destino({"nome": "Bosque dos Buritis", "endereco": "Setor Oeste, Goiania",
                          "lat": -16.6853, "lon": -49.2662})


def passo_navegar(dt):
    app = App.get_running_app()
    app.iniciar_navegacao()
    PASSO["rota"] = app.nav.rota
    PASSO["sim"] = app.gps._sim


def passo_desviar(dt):
    PASSO["sim"].desvio_m = 70.0  # sai da rota pelo lado
    print("[TESTE] desviando 70 m", flush=True)


def passo_desvio_foto(dt):
    app = App.get_running_app()
    foto("10_fora_da_rota")
    PASSO["sim"].desvio_m = 0.0


def passo_recalculou(dt):
    app = App.get_running_app()
    checar(any("Recalculando" in f for f in FALAS), "falou recalculando")
    checar(app.nav is not None and app.nav.rota is not PASSO["rota"], "rota nova depois de sair")
    foto("11_recalculado")


def fim(dt):
    print("[FIM] falas:", FALAS, "erros:", ERROS, flush=True)
    App.get_running_app().stop()


PASSO = {}
Clock.schedule_once(passo_busca, 6)
Clock.schedule_once(passo_busca_foto, 13)
Clock.schedule_once(passo_longe, 14)
Clock.schedule_once(passo_longe_foto, 21)
Clock.schedule_once(passo_destino, 22)
Clock.schedule_once(passo_navegar, 29)
Clock.schedule_once(passo_desviar, 36)
Clock.schedule_once(passo_desvio_foto, 43)
Clock.schedule_once(passo_recalculou, 52)
Clock.schedule_once(fim, 54)
runpy.run_path("main.py", run_name="__main__")
