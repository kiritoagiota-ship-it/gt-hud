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


from viagem import Viagem  # noqa: E402


def destino(dt):
    checar(tela().btn_mais.icone == "mais" and tela().btn_mais.text == "", "botoes de zoom com icone")
    app().escolher_destino({"nome": "Bosque dos Buritis", "endereco": "", "lat": -16.6853, "lon": -49.2662})


def navegar(dt):
    app().iniciar_navegacao()
    sim = app().gps._sim
    original = sim._tick
    sim._ev.cancel()
    sim._ev = Clock.schedule_interval(lambda dt: original(dt * 3), 1 / 3.0)


def ver_nav(dt):
    t = tela()
    checar(t.btn_rotas.icone == "rotas" and t.btn_vivo.icone == "vivo", "Rotas e Ao vivo com icone")
    checar(t.btn_rotas.width == t.btn_mais.width, "coluna de botoes alinhada")
    checar(t._manobra_vista is not None, "manobra acompanhada para animar a troca")
    t.mapa._sair_do_seguir()
    t._montar()
    foto("90_botoes_icones")


def encerrar(dt):
    E["dist"] = app().viagem.distancia_m
    app().encerrar_navegacao()


def ver_resumo(dt):
    t = tela()
    checar(t.card_resumo.parent is not None, "cartao de resumo aparece ao encerrar")
    checar(t.lbl_resumo_titulo.text == "Rota encerrada" and "Buritis" in t.lbl_resumo_destino.text,
           "titulo e destino: %s / %s" % (t.lbl_resumo_titulo.text, t.lbl_resumo_destino.text))
    checar(t.res_dist.valor.text not in ("-", "0 m") and t.res_max.valor.text != "0", "numeros da rota: %s, max %s" % (
        t.res_dist.valor.text, t.res_max.valor.text))
    checar(app().viagem.estado == Viagem.PARADA, "viagem salva")
    foto("91_resumo")
    fechar = [w for w in t.card_resumo.walk() if getattr(w, "text", "") == "Fechar"][0]
    Clock.schedule_once(lambda dt: fechar.dispatch("on_release"), 0.6)


def ver_viagens(dt):
    checar(tela().card_resumo.parent is None, "Fechar tira o cartao")
    app().abrir("viagens")

    def ver(dt):
        v = app().sm.get_screen("viagens")
        titulos = [w.text for w in v.lista.walk() if getattr(w, "bold", False) and getattr(w, "text", "")]
        checar(any(x == "Para Bosque dos Buritis" for x in titulos), "viagem listada pelo destino: %s" % titulos[:2])
        foto("92_viagens_destino")
    Clock.schedule_once(ver, 0.8)


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(destino, 6)
Clock.schedule_once(navegar, 14)
Clock.schedule_once(ver_nav, 22)
Clock.schedule_once(encerrar, 24)
Clock.schedule_once(ver_resumo, 25)
Clock.schedule_once(ver_viagens, 27)
Clock.schedule_once(fim, 30)
runpy.run_path("main.py", run_name="__main__")
