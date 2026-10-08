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




import time  # noqa: E402

AQUI = (-16.7010, -49.2700)      # onde as redes Wi-Fi "dizem" que o celular está


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


def sem_satelite(dt):
    """Como abrir o app num lugar fechado: o satélite não responde."""
    a = app()
    a.gps.parar()
    a.posicao = None
    a._t_valida = a._t_leitura = 0.0
    a.ja_teve_sinal = False
    checar(a.posicao is None and not a.posicao_aproximada, "sem satélite e sem posição nenhuma")


def ruins(dt):
    a = app()
    a.ao_posicao_aproximada(AQUI[0], AQUI[1], 5000.0, 2.0, "network")        # vaga demais
    a.ao_posicao_aproximada(AQUI[0], AQUI[1], 30.0, 5 * 3600.0, "ultima")    # de 5 horas atrás
    a.ao_posicao_aproximada(-23.56, -46.65, 30.0, 2.0, "network")            # São Paulo
    checar(a.posicao is None and not a.posicao_aproximada, "posição vaga, velha ou de outra cidade é ignorada")


def chegou(dt):
    a = app()
    a.gps.modo = "GPS"      # (para o canto do mapa mostrar o texto do celular, não o do simulador)
    a.ao_posicao_aproximada(AQUI[0], AQUI[1], 35.0, 3.0, "network")
    m = tela().mapa
    checar(a.posicao == AQUI and a.posicao_aproximada, "posição aproximada assumida na hora")
    checar(m.eu is not None and abs(m.eu[0] - AQUI[0]) < 1e-9 and m.eu[2] is None and m.eu[3] == 35.0,
           "o mapa mostra o ponto (sem seta de direção) com o círculo de 35 m")
    cor, texto = a.resumo_gps()
    checar(texto.startswith("Posição aproximada"), "aviso claro no canto do mapa: " + texto.replace(chr(10), " "))
    T["viagem"] = len(a.viagem.pontos)


def rota(dt):
    app().escolher_destino({"nome": "Bosque dos Buritis", "endereco": "", "lat": -16.6853, "lon": -49.2662})


def ver_rota(dt):
    a = app()
    checar(a.rota_previa is not None, "já dá para calcular rota com a posição aproximada")
    checar(a.rota_previa is not None and abs(a.rota_previa.pontos[0][0] - AQUI[0]) < 0.003, "a rota sai de onde ele está")
    checar(len(a.viagem.pontos) == T["viagem"], "nada da posição aproximada entra na viagem gravada")
    foto("a0_aproximada")
    a.cancelar_previa()


def satelite(dt):
    """O satélite chegou: ele assume, e a aproximada deixa de valer."""
    a = app()
    a._ao_receber_gps({"lat": -16.7015, "lon": -49.2702, "speed": 0.0, "bearing": None, "accuracy": 6.0})
    checar(not a.posicao_aproximada and a.posicao == (-16.7015, -49.2702), "com o satélite, a posição exata assume")
    a.ao_posicao_aproximada(AQUI[0], AQUI[1], 35.0, 1.0, "network")
    checar(a.posicao == (-16.7015, -49.2702) and not a.posicao_aproximada, "e a posição por rede passa a ser ignorada")
    checar(not a.resumo_gps()[1].startswith("Posição aproximada"), "o aviso some: " + a.resumo_gps()[1].replace(chr(10), " "))


def perdeu(dt):
    """Satélite sumiu há muito tempo (túnel, garagem): a aproximada volta a valer."""
    a = app()
    a._t_valida = time.monotonic() - 60.0
    a.ao_posicao_aproximada(AQUI[0], AQUI[1], 40.0, 1.0, "fused")
    checar(a.posicao == AQUI and a.posicao_aproximada, "um minuto sem satélite: a posição aproximada volta")


T = {}


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(sem_satelite, 7)
Clock.schedule_once(ruins, 7.5)
Clock.schedule_once(chegou, 8)
Clock.schedule_once(rota, 9)
Clock.schedule_once(ver_rota, 15)
Clock.schedule_once(satelite, 16)
Clock.schedule_once(perdeu, 17)
Clock.schedule_once(fim, 18)
runpy.run_path("main.py", run_name="__main__")
