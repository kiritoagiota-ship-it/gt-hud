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


import clima  # noqa: E402
import transito  # noqa: E402

# trânsito e chuva de MENTIRA (sem chave nem internet): o que o app faz com eles
ROTAS = {}


def cidade_falsa(chave, agora=None, baixar=None):
    """Um trânsito lento de 600 m e um acidente em cima da rota em vista."""
    r = ROTAS.get("rota")
    if r is None:
        return []
    lento = [r.ponto_em(d)[:2] for d in range(900, 1501, 40)]
    acidente = r.ponto_em(2200)[:2]
    return [{"categoria": 6, "magnitude": 3, "atraso_s": 300.0, "metros": 600.0, "descricao": "Trânsito parado",
             "de": "", "ate": "", "pontos": lento},
            {"categoria": 1, "magnitude": 2, "atraso_s": 0.0, "metros": 0.0, "descricao": "Acidente",
             "de": "", "ate": "", "pontos": [acidente]}]


transito.da_cidade = cidade_falsa
clima.chuva = lambda origem, destino, duracao_s, prever=None: {"em_min": 15, "onde": "destino", "forte": False}


def destino(dt):
    app().ajustes["tomtom"] = "chave-de-mentira-para-o-teste"
    app().ajustes["avisar_chuva"] = True
    app().ajustes["rota_preferida"] = "rapida"
    real = app()._informar

    def informar(rota, ocorrencias):
        ROTAS["rota"] = rota
        real(rota, cidade_falsa("x"))
    app()._informar = informar
    app().escolher_destino({"nome": "Setor Sudoeste", "endereco": "", "lat": -16.7310, "lon": -49.3050})


def ver_previa(dt):
    t = tela()
    rota = app().rota_previa
    print("[TESTE] avisos:", t.lbl_avisos.text, "| incidentes:", [(round(i["inicio_m"]), i["categoria"]) for i in rota.incidentes], flush=True)
    checar("Chuva prevista em ~15 min no destino" in t.lbl_avisos.text, "previa avisa a chuva")
    checar("min de tr" in t.lbl_avisos.text and "acidente" in t.lbl_avisos.text, "previa mostra o transito: " + t.lbl_avisos.text)
    checar(len(rota.incidentes) == 2 and rota.atraso_transito_s > 120, "rota com 2 ocorrencias e atraso de %.0f s" % rota.atraso_transito_s)
    checar(len(t.mapa._transito) == 1, "trecho de transito pintado no mapa")
    checar(rota.tempo_s > rota.tempo_base_s * 0.5 + 120, "tempo da rota inclui o atraso")
    foto("a0_previa_transito_chuva")


def navegar(dt):
    app().iniciar_navegacao()
    checar(any("previsão de chuva em 15 minutos" in f for f in FALAS), "voz avisa a chuva ao sair: %s" % FALAS[-2:])
    checar(len(app().nav.incidentes) == 2, "navegacao conhece as ocorrencias")
    sim = app().gps._sim
    original = sim._tick
    sim._ev.cancel()
    sim._ev = Clock.schedule_interval(lambda dt: original(dt * 4), 1 / 4.0)


def ver_nav(dt):
    t = tela()
    ditas = [f for f in FALAS if "trânsito lento à frente" in f]
    print("[TESTE] dist:", round(app().nav.dist_feita), "falas:", FALAS[-4:], "chip:", t.lbl_alerta.text, flush=True)
    checar(len(ditas) == 1, "voz avisa o transito lento uma vez: %s" % ditas)
    checar(len(t.mapa._transito) == 1, "transito pintado na navegacao")
    foto("a1_nav_transito")


def fim(dt):
    app().ajustes["tomtom"] = ""   # a chave de mentira não fica para os outros testes
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(destino, 6)
Clock.schedule_once(ver_previa, 20)
Clock.schedule_once(navegar, 21)
Clock.schedule_once(ver_nav, 50)
Clock.schedule_once(fim, 52)
runpy.run_path("main.py", run_name="__main__")
