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


M = 1.0 / 111320.0


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


def janela():
    """A janelinha aberta por cima do app (a mais de cima)."""
    return Window.children[0]


def fechar(dt=None):
    if hasattr(janela(), "dismiss"):
        janela().dismiss()


def zerar():
    a = app()
    a.bateria.carga = None
    a.ajustes["bateria"] = None
    a.ajustes["bateria_cargas"] = []


def comeco(dt):
    zerar()
    t = tela()
    checar(t.btn_bateria.parent is not None, "o botão da bateria está no mapa")
    checar(t.btn_bateria.y >= t.disco.top, "fica acima do velocímetro, sem cobrir")
    t._tique(0)
    checar(t.btn_bateria.text == "Bateria", "sem carga marcada: %r" % t.btn_bateria.text)
    t._abrir_bateria()
    rotulos = [b.text for b in janela().botoes]
    checar(rotulos == ["Carreguei 100%", "Fechar"], "janela antes da 1ª carga: %s" % rotulos)
    Clock.schedule_once(lambda dt: Window.screenshot(name=os.path.join(FOTOS, "b0_primeira_vez.png")), 0.6)
    Clock.schedule_once(fechar, 0.9)


def rodar(dt):
    a, t = app(), tela()
    t._carreguei()                        # 1ª carga: marca direto, sem perguntar
    checar(a.bateria.ativa and a.bateria.metros == 0, "carga cheia marcada")
    lat, lon = -16.68, -49.25
    passo = 45 / 3.6
    for k in range(int(9800 / passo) + 1):
        a.bateria.registrar(lat + k * passo * M, lon, 45.0, float(k))
    t._caiu_barra()
    base = lat + (int(9800 / passo)) * passo * M
    for k in range(1, int(2600 / passo) + 1):
        a.bateria.registrar(base + k * passo * M, lon, 45.0, 1000.0 + k)
    t._tique(0)
    checar(t.btn_bateria.text == "4/5  12,4 km", "botão: %r" % t.btn_bateria.text)
    t._abrir_bateria()
    rotulos = [b.text for b in janela().botoes]
    checar(rotulos == ["Caiu uma barrinha", "Esqueci de marcar uma", "Carreguei 100%",
                       "Desfazer a última barrinha", "Fechar"],
           "janela com a carga contando: %s" % rotulos)
    Clock.schedule_once(lambda dt: Window.screenshot(name=os.path.join(FOTOS, "b1_contando.png")), 0.6)
    Clock.schedule_once(fechar, 0.9)


def recarregar(dt):
    tela()._carreguei()                   # agora pergunta quantas barrinhas sobravam
    rotulos = [b.text for b in janela().botoes]
    checar(rotulos[:6] == ["5 (ainda cheia)", "4", "3", "2", "1", "0 (acabou)"] and rotulos[-1] == "Cancelar",
           "pergunta da sobra: %s" % rotulos)
    Clock.schedule_once(lambda dt: Window.screenshot(name=os.path.join(FOTOS, "b2_sobra.png")), 0.6)
    Clock.schedule_once(lambda dt: janela().botoes[3].dispatch("on_release"), 0.9)   # "2"


def depois(dt):
    a, t = app(), tela()
    cargas = a.ajustes["bateria_cargas"]
    checar(len(cargas) == 1 and cargas[0]["sobra"] == 2 and abs(cargas[0]["m"] - 12400) < 60,
           "a carga foi para o histórico: %s" % cargas)
    checar(t.btn_bateria.text == "5/5  0,0 km", "botão depois de recarregar: %r" % t.btn_bateria.text)
    checar("uns 21 km" in a.bateria.texto(), "autonomia pelo uso (12,4 km em 3 barrinhas): %s" % a.bateria.texto())
    t._abrir_bateria()
    checar("Cargas anteriores" in [b.text for b in janela().botoes], "histórico disponível")
    fechar()
    t._ver_cargas()
    Clock.schedule_once(lambda dt: Window.screenshot(name=os.path.join(FOTOS, "b3_historico.png")), 0.6)
    Clock.schedule_once(fechar, 0.9)


def fim(dt):
    zerar()
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(comeco, 7)
Clock.schedule_once(rodar, 8.5)
Clock.schedule_once(recarregar, 10)
Clock.schedule_once(depois, 11.5)
Clock.schedule_once(fim, 13.5)
runpy.run_path("main.py", run_name="__main__")
