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




import time  # noqa: E402

import transito  # noqa: E402
import widgets.comuns  # noqa: E402

M = 1.0 / 111320.0
PEDIDOS = []
ABERTOS = []


def app():
    return App.get_running_app()


def cidade_falsa(chave, agora=None, baixar=None):
    """4 ocorrências em volta de quem pedala (a TomTom de verdade não entra no teste)."""
    PEDIDOS.append(chave)
    lat, lon = app().posicao
    lento = [(lat + 60 * M + k * 25 * M, lon - 90 * M) for k in range(8)]
    obras = [(lat - 80 * M, lon - 60 * M + k * 30 * M) for k in range(5)]
    return [
        {"categoria": 6, "magnitude": 3, "atraso_s": 240.0, "metros": 200.0, "descricao": "Trânsito parado",
         "de": "Rua 10", "ate": "Avenida Goiás", "pontos": lento},
        {"categoria": 1, "magnitude": 2, "atraso_s": 0.0, "metros": 0.0, "descricao": "Acidente",
         "de": "Avenida Araguaia", "ate": "", "pontos": [(lat + 70 * M, lon + 80 * M)]},
        {"categoria": 9, "magnitude": 1, "atraso_s": 30.0, "metros": 120.0, "descricao": "Obras na pista",
         "de": "Rua 3", "ate": "Rua 4", "pontos": obras},
        {"categoria": 8, "magnitude": 4, "atraso_s": 0.0, "metros": 60.0, "descricao": "Via interditada",
         "de": "Rua 82", "ate": "", "pontos": [(lat - 30 * M, lon + 110 * M), (lat - 30 * M, lon + 150 * M)]}]


transito.da_cidade = cidade_falsa
_escolher = widgets.comuns.escolher


class ToqueFalso:
    def __init__(self, x, y):
        self.x, self.y, self.pos = x, y, (x, y)
        self.ud, self.time_start = {}, time.time()
        self.is_double_tap = False
        self.grab_current = None

    def grab(self, w):
        self.grab_current = w

    def ungrab(self, w):
        self.grab_current = None


def ligar(dt):
    app().ajustes["tomtom"] = "chave-de-mentira-para-o-teste"
    app().atualizar_transito_do_mapa()


def ver_mapa(dt):
    mapa = app().sm.get_screen("mapa").mapa
    checar(PEDIDOS == ["chave-de-mentira-para-o-teste"], "o mapa pediu o trânsito da cidade (sem rota nenhuma)")
    checar(len(mapa.ocorrencias) == 4, "4 ocorrências no mapa: %d" % len(mapa.ocorrencias))
    checar(len(mapa._larg_geral) == 3, "3 trechos pintados (lento, obras, interditada): %d" % len(mapa._larg_geral))
    checar(len(mapa._ocorr_na_tela) == 4, "4 ícones à vista: %d" % len(mapa._ocorr_na_tela))
    checar(app().nav is None and app().destino is None, "tudo isso em modo livre, sem destino")
    foto("t0_transito_no_mapa")


def tocar(dt):
    tela = app().sm.get_screen("mapa")
    mapa = tela.mapa
    vistos = []
    real = mapa.ao_tocar_ocorrencia
    mapa.ao_tocar_ocorrencia = lambda o: (vistos.append(o), real(o))
    acidente = next(i for i in mapa._ocorr_na_tela if i[2]["categoria"] == 1)
    sx, sy = mapa._local_para_tela(acidente[0], acidente[1])
    longe = ToqueFalso(sx + dp(80), sy + dp(80))       # toque fora de qualquer ícone: nada abre
    mapa.on_touch_down(longe)
    mapa.on_touch_up(longe)
    checar(not vistos, "tocar fora dos ícones não abre nada")
    perto = ToqueFalso(sx + dp(8), sy - dp(6))
    mapa.on_touch_down(perto)
    mapa.on_touch_up(perto)
    checar(len(vistos) == 1 and vistos[0]["categoria"] == 1, "tocar no ícone abre o acidente")
    mapa.ao_tocar_ocorrencia = real
    Clock.schedule_once(lambda dt: foto("t1_cartao_do_acidente"), 0.6)


def fechar(dt):
    from kivy.uix.modalview import ModalView
    for w in list(Window.children):
        if isinstance(w, ModalView):
            w.dismiss()


def ajustes(dt):
    app().abrir("config")
    Clock.schedule_once(lambda dt: app().sm.get_screen("config")._testar_transito(), 0.8)


def ver_ajustes(dt):
    c = app().sm.get_screen("config")
    texto = c.linha_testar_transito.explicacao.text
    checar(texto.startswith("Funcionando: 4 ocorrências em Goiânia agora"), "Ajustes prova que funciona: " + texto)
    rol = [w for w in c.walk() if w.__class__.__name__ == "ScrollView"][0]
    rol.scroll_to(c.linha_testar_transito)
    Clock.schedule_once(lambda dt: foto("t2_ajustes_testar"), 0.8)


def recusada(dt):
    def recusa(chave, agora=None, baixar=None):
        raise transito.SemChave("A TomTom recusou a chave.")
    transito.da_cidade = recusa
    app().sm.get_screen("config")._testar_transito()


def ver_recusada(dt):
    c = app().sm.get_screen("config")
    checar("RECUSOU" in c.linha_testar_transito.explicacao.text, "chave recusada aparece claro nos Ajustes")
    checar("chave-de-mentira" not in c.linha_testar_transito.explicacao.text, "a chave não aparece na tela")


def fim(dt):
    app().ajustes["tomtom"] = ""   # a chave de mentira não fica para os outros testes
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(ligar, 7)
Clock.schedule_once(ver_mapa, 9)
Clock.schedule_once(tocar, 10)
Clock.schedule_once(fechar, 12)
Clock.schedule_once(ajustes, 13)
Clock.schedule_once(ver_ajustes, 16)
Clock.schedule_once(recusada, 18)
Clock.schedule_once(ver_recusada, 20)
Clock.schedule_once(fim, 21)
runpy.run_path("main.py", run_name="__main__")
