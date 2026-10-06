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


def b():
    return app().sm.get_screen("busca")


def janelas():
    return [w for w in Window.children if isinstance(w, Popup)]


def abrir(dt):
    app().ajustes["atalhos"] = {}
    app().abrir("busca")
    Clock.schedule_once(lambda dt: checar(b().btn_atalho["casa"].text == "+ Casa", "atalho vazio mostra + Casa"), 0.3)
    Clock.schedule_once(lambda dt: setattr(b().campo, "text", "farmac"), 0.5)     # só digita, sem Buscar


def ver_digitando(dt):
    n = len(b().lista.children)
    checar(n >= 5, "digitando ja lista do celular (%d): %s" % (n, b().lbl_status.text))
    checar("no celular" in b().lbl_status.text, "aviso de que e so o celular")
    foto("70_digitando")
    b().campo.text = ""


def definir_casa(dt):
    checar(b().lbl_status.text.startswith("Salvos") or "Digite" in b().lbl_status.text, "apagou o texto: volta aos recentes")
    bt = b().btn_atalho["casa"]
    bt.dispatch("on_press")
    bt.dispatch("on_release")
    pop = janelas()
    checar(len(pop) == 1 and "Escolher na busca" in [x.text for x in pop[0].botoes], "tocar no atalho vazio pergunta como definir")
    [x for x in pop[0].botoes if x.text == "Escolher na busca"][0].dispatch("on_release")
    Clock.schedule_once(lambda dt: setattr(b().campo, "text", "bosque dos buritis"), 0.3)


def escolher_casa(dt):
    checar(b()._definindo == "casa" and len(b().lista.children) >= 1, "modo definir Casa com resultados")
    foto("71_definindo_casa")
    item = b().lista.children[-1]
    alvo = item.children[-1] if not hasattr(item, "state") else item
    alvo.dispatch("on_release")


def ver_casa(dt):
    casa = app().ajustes["atalhos"].get("casa")
    checar(casa is not None and "Buritis" in casa["nome"], "Casa definida: %s" % (casa or {}).get("nome"))
    checar(app().destino is None, "definir nao traca rota")
    checar(b().btn_atalho["casa"].text == "Casa", "botao virou Casa")
    bt = b().btn_atalho["trabalho"]            # trabalho: "é aqui"
    bt.dispatch("on_press")
    bt.dispatch("on_release")
    pop = janelas()
    aqui = [x for x in pop[0].botoes if x.text.startswith("É aqui")] if pop else []
    checar(len(aqui) == 1, "oferece usar a posicao atual")
    if aqui:
        aqui[0].dispatch("on_release")


def ir_para_casa(dt):
    checar("trabalho" in app().ajustes["atalhos"], "Trabalho definido aqui")
    foto("72_atalhos_prontos")
    bt = b().btn_atalho["casa"]
    bt.dispatch("on_press")
    bt.dispatch("on_release")


def ver_rota(dt):
    checar(app().destino is not None and "Buritis" in app().destino["nome"], "um toque em Casa tracou a rota")
    checar(app().sm.current == "mapa", "foi para o mapa")
    app().cancelar_previa()
    app().abrir("busca")
    bt = b().btn_atalho["casa"]                # segurar: trocar/apagar
    bt.dispatch("on_press")


def ver_segurar(dt):
    pop = janelas()
    checar(len(pop) == 1 and "Apagar" in [x.text for x in pop[0].botoes], "segurar o atalho oferece trocar/apagar")
    b().btn_atalho["casa"].dispatch("on_release")
    checar(app().destino is None, "segurar nao traca rota")
    if pop:
        [x for x in pop[0].botoes if x.text == "Apagar"][0].dispatch("on_release")
    checar("casa" not in app().ajustes["atalhos"], "Casa apagada")


def ajustes(dt):
    app().abrir("config")

    def ver(dt):
        from telas.config import Secao
        cfg = app().sm.get_screen("config")
        nomes = [w.lbl.text for w in cfg.walk() if isinstance(w, Secao)]
        checar(nomes == ["VOZ", "NAVEGAÇÃO", "MAPA E TELA", "VELOCÍMETRO E VIAGEM", "SISTEMA"], "Ajustes em secoes: %s" % nomes)
        foto("73_ajustes_secoes")
    Clock.schedule_once(ver, 0.8)


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(abrir, 6)
Clock.schedule_once(ver_digitando, 8)
Clock.schedule_once(definir_casa, 9)
Clock.schedule_once(escolher_casa, 11)
Clock.schedule_once(ver_casa, 12)
Clock.schedule_once(ir_para_casa, 13)
Clock.schedule_once(ver_rota, 20)
Clock.schedule_once(ver_segurar, 21.5)
Clock.schedule_once(ajustes, 23)
Clock.schedule_once(fim, 25.5)
runpy.run_path("main.py", run_name="__main__")
