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



from kivy.uix.popup import Popup  # noqa: E402
from kivy.uix.textinput import TextInput  # noqa: E402

E = {}


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


import threading  # noqa: E402

import ao_vivo  # noqa: E402
import rede  # noqa: E402
from ferramentas.firebase_falso import servidor  # noqa: E402
from viagem import Viagem  # noqa: E402

HTTP, BANCO, BASE = servidor()


def janelas():
    return [w for w in Window.children if isinstance(w, Popup)]


def renomear(dt):
    app().ajustes["firebase"] = BASE
    app().ajustes["corridas_abertas"] = []
    app().salvos = [{"nome": "Plus Code 9MJH+9W", "endereco": "", "lat": -16.61906, "lon": -49.32019}]
    app().recentes = [{"nome": "Plus Code 9MJH+9W", "endereco": "", "lat": -16.61906, "lon": -49.32019}]
    app().abrir("busca")

    def tocar(dt):
        b = app().sm.get_screen("busca")
        editar = [w for w in b.walk() if getattr(w, "text", "") == "Editar"]
        checar(len(editar) == 1, "lugar salvo tem botao Editar")
        editar[0].dispatch("on_release")
        pop = janelas()
        checar(len(pop) == 1 and pop[0].botoes[0].text == "Trocar o nome", "Editar oferece trocar o nome")
        pop[0].botoes[0].dispatch("on_release")

        def digitar(dt):
            pop = janelas()
            checar(len(pop) == 1 and pop[0].campo.text == "", "pergunta o nome novo (campo vazio: o antigo era so o codigo)")
            pop[0].campo.text = "Barbearia Imagem"
            pop[0].confirmar()
            checar(app().salvos[0]["nome"] == "Barbearia Imagem", "salvo renomeado: %s" % app().salvos)
            checar(app().recentes[0]["nome"] == "Barbearia Imagem", "o recente do mesmo ponto tambem")
            itens = [w for w in b.walk() if w.__class__.__name__ == "ItemViagem"]
            checar(len(itens) == 1, "lista mostra o lugar uma vez so (%d)" % len(itens))
            foto("80_renomeado")
        Clock.schedule_once(digitar, 0.5)
    Clock.schedule_once(tocar, 0.6)


def destino(dt):
    app().sm.current = "mapa"
    app().escolher_destino({"nome": "Bosque dos Buritis", "endereco": "", "lat": -16.6853, "lon": -49.2662})


def navegar(dt):
    app().iniciar_navegacao()
    tela().btn_vivo.dispatch("on_release")
    checar(app().compartilhando(), "compartilhando ao vivo")
    E["codigo"] = app().corrida.codigo


def chegar_minimizado(dt):
    """Minimiza e "anda" até o destino pela thread de segundo plano. O relógio
    do Kivy fica de fora (no celular ele PARA com o app minimizado)."""
    app().gps._sim.parar()
    app().on_pause()
    checar(app().fundo.minimizado, "minimizado")
    real = app().conferir_fim
    E["threads"] = []

    def so_no_fundo():
        if threading.current_thread().name == "MainThread" and app().fundo.minimizado:
            return                       # Clock parado no celular
        E["threads"].append(threading.current_thread().name)
        real()
    app().conferir_fim = so_no_fundo
    fim_rota = app().nav.rota.pontos[-1]
    leitura = {"lat": fim_rota[0], "lon": fim_rota[1], "speed": 2.0, "bearing": 0.0, "accuracy": 5.0}

    def gps_falso():
        return dict(leitura)
    app().gps.ler_direto = gps_falso     # a thread de segundo plano le o GPS direto


def ver_chegou(dt):
    pub = rede.baixar_json("%s/corridas/%s/pub.json" % (BASE, E["codigo"]))
    checar((pub.get("pos") or {}).get("e") == "chegou", "quem acompanha ve CHEGOU na hora: %s" % pub.get("pos"))


def ver_encerrou(dt):
    checar(app().nav is None, "rota encerrada sozinha com o app minimizado")
    checar(app().viagem.estado == Viagem.PARADA, "viagem salva e parada")
    checar("segundo-plano" in E["threads"], "quem encerrou foi a thread de segundo plano")
    checar(app().fundo._ligado is False, "servico de segundo plano desligado")
    app().gps.ler_direto = lambda: None
    app().on_resume()

    def de_volta(dt):
        checar(tela().estado == "livre", "ao voltar, o mapa esta no modo livre")
        checar(app().ajustes["corridas_abertas"] == [], "nenhuma corrida aberta sobrando")
        foto("81_chegou_minimizado")
    Clock.schedule_once(de_volta, 1.0)


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(renomear, 5)
Clock.schedule_once(destino, 8)
Clock.schedule_once(navegar, 16)
Clock.schedule_once(chegar_minimizado, 18)
Clock.schedule_once(ver_chegou, 21)
Clock.schedule_once(ver_encerrou, 26.5)
Clock.schedule_once(fim, 29)
runpy.run_path("main.py", run_name="__main__")
