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

from util import fmt_dist_nav, fmt_duracao  # noqa: E402

import rede  # noqa: E402
import rota as rotas  # noqa: E402

# a resposta da rota demora um pouco de propósito: dá tempo de ver (e fotografar) o radar
_pedir = rotas.pedir_rota


def pedir_devagar(*a, **k):
    time.sleep(1.3)
    return _pedir(*a, **k)


rotas.pedir_rota = pedir_devagar

TILES_BAIXADOS = []
_baixar = rede.baixar


def baixar_contando(url, timeout=20):
    if url.endswith(".pbf"):
        TILES_BAIXADOS.append(url)
    return _baixar(url, timeout)


rede.baixar = baixar_contando

FOTO = {}       # tirar a foto do teste custa ~200 ms: esse quadro não entra na conta
Q = []          # (segundos desde a escolha, ms do quadro)
ULT = {"t": None}
T0 = {}
VISTO = {}


_foto = foto


def foto(nome):
    _foto(nome)
    Clock.schedule_once(lambda dt: FOTO.__setitem__("agora", True), 0)


def app():
    return App.get_running_app()


def medir(dt):
    agora = time.perf_counter()
    if ULT["t"] is not None and "ini" in T0 and not FOTO.pop("agora", False):
        Q.append((agora - T0["ini"], (agora - ULT["t"]) * 1000))
    ULT["t"] = agora
    if "ini" in T0:
        mapa = app().sm.get_screen("mapa").mapa
        if mapa._voo is not None:
            VISTO["voo"] = True
        if mapa._revelar is not None and "revelar" not in VISTO:
            VISTO["revelar"] = agora - T0["ini"]
            Clock.schedule_once(lambda dt: foto("p1_rota_se_desenhando"), 0.5)
        if mapa._brilho is not None:
            VISTO["brilho"] = True


def escolher(dt):
    tela = app().sm.get_screen("mapa")
    T0["ini"] = time.perf_counter()
    t = time.perf_counter()
    app().escolher_destino({"nome": "Setor Sudoeste", "endereco": "", "lat": -16.7200, "lon": -49.2950})
    gasto = (time.perf_counter() - t) * 1000
    mapa = tela.mapa
    checar(gasto < 40, "escolher o destino não segura a tela (%.0f ms)" % gasto)
    checar(mapa._radar_t0 is not None, "radar procurando caminho ligado")
    checar(mapa._dest_t0 is not None, "pino do destino caindo")
    checar(tela._card_fora > 0.9 and tela._ev_card is not None, "cartão entrando deslizando")
    checar(tela.lbl_resumo.text == "Calculando a rota...", "cartão diz que está calculando")


def procurando(dt):
    tela = app().sm.get_screen("mapa")
    checar(tela.mapa._radar_t0 is not None, "radar ainda ligado enquanto a rota não chega")
    checar(tela.mapa._voo is not None or VISTO.get("voo"), "câmera voando até caberem os dois pontos")
    checar(tela._card_fora == 0.0 and tela.card.y == dp(10), "cartão chegou ao lugar")
    foto("p0_procurando")


def pronta(dt):
    tela = app().sm.get_screen("mapa")
    mapa = tela.mapa
    rota = app().rota_previa
    checar(rota is not None, "rota chegou")
    checar(VISTO.get("revelar") is not None, "a rota se desenhou aos poucos")
    checar(VISTO.get("brilho"), "clarão quando a rota termina de se desenhar")
    checar(mapa._revelar is None and mapa._voo is None and mapa._radar_t0 is None and mapa._brilho is None,
           "animações terminaram (nada fica rodando à toa)")
    checar(rota is not None and tela.lbl_resumo.text.startswith("%s  |  %s  |  sobe %d m" % (
        fmt_dist_nav(rota.total_m), fmt_duracao(rota.tempo_s), rota.subida_total_m)),
           "números do cartão pararam no valor certo: " + tela.lbl_resumo.text)
    linhas = [l for l, _ in mapa._larg_rota]
    checar(rota is not None and any(len(l.points) == 2 * len(rota.pontos) for l in linhas),
           "linha final da rota com todos os pontos")
    checar(not TILES_BAIXADOS, "mapa veio de dentro do app: %d pedaços baixados da internet" % len(TILES_BAIXADOS))
    lentos = [(round(a, 2), round(ms)) for a, ms in Q if ms > 34]
    pior = max((ms for _, ms in Q), default=0)
    print("[QUADROS] %d quadros, pior %.0f ms, acima de 34 ms: %s" % (len(Q), pior, lentos), flush=True)
    checar(pior < 90, "nenhuma travada na escolha do destino (pior quadro %.0f ms)" % pior)
    foto("p2_rota_pronta")


def trocar(dt):
    """Escolher outra opção de rota também desenha a linha (mais rápido)."""
    a = app()
    outras = [r for r in a.rotas_previa if r is not a.rota_previa]
    if not outras:
        print("[TESTE] só veio uma rota: sem troca para testar", flush=True)
        return
    VISTO.pop("revelar", None)
    a.escolher_rota_previa(outras[0])
    mapa = a.sm.get_screen("mapa").mapa
    checar(mapa._revelar is not None, "trocar de opção desenha a rota nova")


def cancelar(dt):
    a = app()
    a.cancelar_previa()
    tela = a.sm.get_screen("mapa")
    checar(tela.mapa._revelar is None and tela.mapa._radar_t0 is None and tela._rota_na_tela is None,
           "cancelar limpa as animações")


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_interval(medir, 0)
Clock.schedule_once(escolher, 8)
Clock.schedule_once(procurando, 8.9)
Clock.schedule_once(pronta, 14)
Clock.schedule_once(trocar, 24)
Clock.schedule_once(cancelar, 27)
Clock.schedule_once(fim, 28)
runpy.run_path("main.py", run_name="__main__")
