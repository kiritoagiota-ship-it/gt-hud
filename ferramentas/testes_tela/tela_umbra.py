"""Teste de TELA do GT-HUD (janela no 2º monitor): o Umbra. Rodar por
ferramentas/testes_tela/rodar_todos.py (que isola APPDATA/KIVY_HOME).

Chamado pelo botão: aparece grande, cumprimenta, ouve "me leva pra casa", traça e começa a
rota sozinho. Com a rota andando: num aviso (radar) aparece pequeno e some. Parado, com o
microfone liberado: o nome "Umbra" chama ele. (No PC o que é "dito" entra por escuta.dizer.)"""
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

RAIZ = os.path.dirname(os.path.dirname(PASTA))  # raiz do projeto
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
sys.path.insert(0, PASTA)
import caminhos  # noqa: E402,F401  (as pastas do código no caminho de busca)
sys.argv = ["main.py"]

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402

import rota_falsa  # noqa: E402
import umbra  # noqa: E402
import voz  # noqa: E402

rota_falsa.instalar()
DITAS = []
ERROS = []


def falar_falso(self, pedacos, prioridade=1, texto=None, nervosa=False):
    """Sem som no teste: anota a fala e finge que ela dura 1,2 s (a boca mexe, o Umbra espera)."""
    DITAS.append(pedacos[-1])
    print("[FALA]", pedacos, flush=True)
    agora = time.monotonic()
    self._livre_em = agora + 1.2
    self._comecou(pedacos, None, agora, 1.2)


voz.Voz.falar = falar_falso


def checar(cond, texto):
    print("[CHECA]", "OK " if cond else "FALHOU", texto, flush=True)
    if not cond:
        ERROS.append(texto)


def foto(nome):
    Window.screenshot(name=os.path.join(FOTOS, nome + ".png"))
    print("[FOTO]", nome, flush=True)


def app():
    return App.get_running_app()


def rosto():
    return app().sm.get_screen("mapa").rosto_umbra


def comeco(dt):
    a = app()
    if a.posicao is None:
        a.posicao = (-16.6869, -49.2648)
    a.ajustes["atalhos"] = {"casa": {"nome": "Casa", "lat": -16.6990, "lon": -49.2580}}
    a.umbra.microfone = False             # primeiro pelo botão (a escuta do nome fica parada)
    a.velocidade_agora = lambda: 0.0      # parado (andando, ele viria médio: ver medio())
    t = a.sm.get_screen("mapa")
    checar(t.btn_umbra.parent is not None, "o botão do Umbra está no mapa")
    checar(t.btn_umbra.x > t.width / 2, "na coluna de botões da direita")
    a.escuta.dizer("me leva pra casa")
    t.btn_umbra.dispatch("on_release")
    checar(a.umbra.estado == umbra.SAUDANDO, "chamado pelo botão: cumprimenta (%s)" % a.umbra.estado)
    checar(rosto().modo == "grande", "aparece grande")
    checar(not rosto().quebrado, "o desenho do rosto compilou")


def grande(dt):
    foto("u1_grande")
    checar(rosto().presenca > 0.9, "inteiro na tela (presença %.2f)" % rosto().presenca)
    checar(rosto()._cor_veu.a > 0.5, "o mapa por trás escurece (véu %.2f)" % rosto()._cor_veu.a)
    checar(any(d.startswith("umbra_oi") for d in DITAS), "cumprimentou: %s" % DITAS)


def rota(dt):
    a = app()
    checar("umbra_casa" in DITAS, "entendeu o pedido e respondeu: %s" % DITAS)
    checar(a.nav is not None, "a rota para casa começou sozinha")
    checar(rosto().modo is None, "ele saiu da tela")
    foto("u2_navegando")


def aviso(dt):
    app().voz.falar(["senhor", "em_200", "radar"], 2)
    checar(rosto().modo == "pequeno", "aviso de radar com rota: aparece pequeno")


def aviso_foto(dt):
    foto("u3_pequeno")
    t = app().sm.get_screen("mapa")
    topo = rosto().ry + rosto().rlado
    checar(t.faixa.y - 30 <= topo <= t.faixa.y + 1,
           "pequeno logo abaixo da faixa da curva (topo dele %.0f; faixa a partir de %.0f)" % (topo, t.faixa.y))


def sumiu(dt):
    checar(rosto().modo is None, "depois do aviso, sumiu")
    a = app()
    a.encerrar_navegacao()
    a.velocidade_agora = lambda: 0.0      # parado
    a.umbra.microfone = True
    a.escuta.dizer("umbra")
    a.escuta.dizer("valeu")


def por_nome(dt):
    foto("u4_depois_do_nome")
    # (qualquer variação gravada do "valeu": umbra_valeu, umbra_valeu_2...)
    checar(any(d.startswith("umbra_valeu") for d in DITAS), "chamado pelo nome, respondeu o 'valeu': %s" % DITAS[-4:])


def medio(dt):
    # chamado com a moto andando: médio no canto, sem escurecer o mapa (pedido do dono, 14/10/2026)
    a = app()
    a.umbra.microfone = False
    a.velocidade_agora = lambda: 25.0
    a.umbra.chamar()
    checar(rosto().modo == "medio", "andando: aparece médio (%s)" % rosto().modo)


def fumaca_foto(dt):
    foto("u5_fumaca")
    checar(0.05 < rosto().presenca < 0.95, "no meio da entrada (presença %.2f)" % rosto().presenca)


def medio_foto(dt):
    foto("u6_medio")
    r, t = rosto(), app().sm.get_screen("mapa")
    checar(r._cor_veu.a < 0.01, "médio: o mapa não escurece (véu %.2f)" % r._cor_veu.a)
    checar(r.rx > t.width / 2 and r.rlado < t.width * 0.6, "médio: no canto da direita, menor que o grande")


def farejando(dt):
    a = app()
    a.umbra.fechar()
    a.velocidade_agora = lambda: 0.0
    r = rosto()
    r.mostrar("grande")
    r.definir_estado("farejando")


def farejando_foto(dt):
    foto("u7_farejando")
    checar(rosto().mov.estado == "farejando", "cara de farejando")
    rosto().esconder()


def simples(dt):
    # o modo simples (imagens prontas): o que o app usa se o desenho ao vivo derrubar o app
    a = app()
    a.umbra.microfone = False
    r = rosto()
    r.simples = True
    a.escuta.dizer("valeu")
    a.umbra.chamar()
    checar(r.modo == "grande" and r._ret_img.texture is not None, "modo simples: aparece com a imagem")


def simples_foto(dt):
    foto("u5_simples")
    checar(rosto().presenca > 0.9, "modo simples na tela")


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(comeco, 7)
Clock.schedule_once(grande, 8.0)
Clock.schedule_once(rota, 13.0)
Clock.schedule_once(aviso, 13.5)
Clock.schedule_once(aviso_foto, 13.9)
Clock.schedule_once(sumiu, 16.0)
Clock.schedule_once(por_nome, 30.0)
Clock.schedule_once(medio, 31.0)
Clock.schedule_once(fumaca_foto, 31.25)
Clock.schedule_once(medio_foto, 32.2)
Clock.schedule_once(farejando, 33.0)
Clock.schedule_once(farejando_foto, 34.4)
Clock.schedule_once(simples, 35.4)
Clock.schedule_once(simples_foto, 36.2)
Clock.schedule_once(fim, 39.0)
runpy.run_path("main.py", run_name="__main__")
