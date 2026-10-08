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




import tema  # noqa: E402

tema.e_noite = lambda lat, lon, quando=None: True      # o teste roda de dia: aqui é sempre noite


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


def longe(dt):
    """Da zona oeste até o Passeio das Águas: a noturna é um caminho diferente da rápida."""
    a = app()
    a.gps._sim.lat, a.gps._sim.lon = -16.628, -49.330
    a.posicao = (-16.628, -49.330)
    a.ajustes["rota_preferida"] = "tranquila"
    a.escolher_destino({"nome": "Passeio das Águas Shopping", "endereco": "", "lat": -16.6368, "lon": -49.2600})


def ver(dt):
    a = app()
    t = tela()
    nomes = [r.nome_perfil for r in a.rotas_previa]
    print("[TESTE] rotas:", [(r.nome_perfil, round(r.tempo_s / 60), None if r.movimentada is None else round(r.movimentada * 100))
                             for r in a.rotas_previa], flush=True)
    noturna = next((r for r in a.rotas_previa if r.perfil == "noturna"), None)
    checar(noturna is not None, "à noite aparece a rota noturna: %s" % nomes)
    abas = [b.text.split(chr(10))[0] for b in t.escolha.children[::-1] if hasattr(b, "text") and "min" in b.text]
    checar("Noturna" in abas, "aba Noturna no cartão: %s" % abas)
    calma = next((r for r in a.rotas_previa if "tranquila" in r.nome_perfil), None)
    if calma is not None:
        a.escolher_rota_previa(calma)
        checar("ruas mais vazias" in t.lbl_avisos.text, "aviso na Tranquila à noite: " + t.lbl_avisos.text)
        foto("n0_tranquila_de_noite")
    else:
        print("[TESTE] sem rota tranquila neste trajeto: aviso não conferido", flush=True)
    T["noturna"] = noturna


def ver_noturna(dt):
    a, t = app(), tela()
    if T.get("noturna") is None:
        return
    a.escolher_rota_previa(T["noturna"])
    checar("ruas principais" in t.lbl_avisos.text, "a Noturna diz que vai pelas ruas principais: " + t.lbl_avisos.text)
    Clock.schedule_once(lambda dt: foto("n1_noturna"), 1.0)


T = {}


def fim(dt):
    app().ajustes["rota_preferida"] = "rapida"
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(longe, 7)
Clock.schedule_once(ver, 34)
Clock.schedule_once(ver_noturna, 36)
Clock.schedule_once(fim, 39)
runpy.run_path("main.py", run_name="__main__")
