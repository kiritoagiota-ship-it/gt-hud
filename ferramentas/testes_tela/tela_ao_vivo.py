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


import ao_vivo  # noqa: E402
import rede  # noqa: E402
from ferramentas.firebase_falso import servidor  # noqa: E402
from kivy.core.clipboard import Clipboard  # noqa: E402
from viagem import Viagem  # noqa: E402

HTTP, BANCO, BASE = servidor()
ao_vivo.ENVIAR_A_CADA_S = 1.0


def botoes(texto):
    return [w for w in app().root.walk() if getattr(w, "text", "") == texto and w.parent is not None]


def livre(dt):
    app().ajustes["firebase"] = ""            # (os ajustes dos testes ficam de uma rodada para outra)
    app().ajustes["corridas_abertas"] = []
    checar(not botoes("Gravar viagem"), "modo livre sem botao de gravar")
    checar(app().viagem.estado == Viagem.PARADA, "andando livre nao grava")
    checar(tela().col_dist.rotulo.text == "hoje", "barra livre mostra o total de hoje")
    foto("50_livre_sem_gravar")
    app().escolher_destino({"nome": "Destino teste", "endereco": "", "lat": -16.7310, "lon": -49.3050})


def navegar(dt):
    app().iniciar_navegacao()
    checar(app().viagem.estado == Viagem.GRAVANDO, "rota iniciada grava sozinha")
    sim = app().gps._sim
    original = sim._tick
    sim._ev.cancel()
    sim._ev = Clock.schedule_interval(lambda dt: original(dt * 3), 1 / 3.0)


def sem_config(dt):
    checar(tela().btn_vivo.parent is not None and tela().btn_vivo.text == "Ao vivo", "botao Ao vivo na navegacao")
    tela().btn_vivo.dispatch("on_release")
    pop = [w for w in Window.children if isinstance(w, Popup)]
    checar(len(pop) == 1 and not app().compartilhando(), "sem o banco configurado: explica e nao compartilha")
    foto("51_ao_vivo_sem_config")
    for p in pop:
        p.dismiss()


def compartilhar(dt):
    app().ajustes["firebase"] = BASE
    tela().btn_vivo.dispatch("on_release")
    checar(app().compartilhando(), "compartilhando")
    colado = Clipboard.paste()
    checar(app().corrida.link in colado and "Acompanhe" in colado, "texto com o link pronto para enviar: %r" % colado[:60])
    checar(tela().btn_vivo.text == "No ar", "botao mostra No ar")
    checar(len(app().ajustes["corridas_abertas"]) == 1, "corrida anotada como aberta")
    E["codigo"] = app().corrida.codigo


def ver_banco(dt):
    pub = rede.baixar_json("%s/corridas/%s/pub.json" % (BASE, E["codigo"]))
    pos = pub.get("pos") or {}
    checar(pub.get("destino") == "Destino teste" and "linha" in (pub.get("rota") or {}), "destino e rota no banco")
    checar(pos.get("e") == "indo" and pos.get("fm", 0) > 1000 and pos.get("v", 0) > 0, "posicao ao vivo no banco: %s" % pos)
    checar(len(pub.get("tr") or {}) >= 1, "caminho feito no banco (%d pedacos)" % len(pub.get("tr") or {}))
    foto("52_ao_vivo_no_ar")
    tela().btn_vivo.dispatch("on_release")
    pop = [w for w in Window.children if isinstance(w, Popup)]
    checar(len(pop) == 1 and [b.text for b in pop[0].botoes][:2] == ["Enviar o link de novo", "Parar de compartilhar"],
           "tocar de novo oferece reenviar ou parar")
    if pop:
        Clock.schedule_once(lambda dt: pop[0].botoes[1].dispatch("on_release"), 0.4)


def ver_parou(dt):
    pub = rede.baixar_json("%s/corridas/%s/pub.json" % (BASE, E["codigo"]))
    checar(pub["pos"].get("e") == "encerrou" and "lat" not in pub["pos"] and "tr" not in pub and "rota" not in pub,
           "parou: posicao, rota e caminho apagados do banco")
    checar(not app().compartilhando() and tela().btn_vivo.text == "Ao vivo", "botao voltou ao normal")
    checar(app().ajustes["corridas_abertas"] == [], "nenhuma corrida aberta sobrando")
    checar(app().nav is not None, "a navegacao continua")
    tela().btn_vivo.dispatch("on_release")   # compartilha de novo e encerra a rota: deve fechar sozinho
    E["codigo2"] = app().corrida.codigo
    Clock.schedule_once(lambda dt: app().encerrar_navegacao(), 2.5)


def ver_fim(dt):
    pub = rede.baixar_json("%s/corridas/%s/pub.json" % (BASE, E["codigo2"]))
    checar(E["codigo2"] != E["codigo"] and pub["pos"].get("e") == "encerrou", "encerrar a rota encerra o ao vivo")
    checar(app().viagem.estado == Viagem.PARADA, "rota encerrada: gravacao parou sozinha")
    checar(app().ajustes["corridas_abertas"] == [], "nada aberto no fim")


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(livre, 6)
Clock.schedule_once(navegar, 16)
Clock.schedule_once(sem_config, 18)
Clock.schedule_once(compartilhar, 19)
Clock.schedule_once(ver_banco, 25)
Clock.schedule_once(ver_parou, 28)
Clock.schedule_once(ver_fim, 34)
Clock.schedule_once(fim, 36)
runpy.run_path("main.py", run_name="__main__")
