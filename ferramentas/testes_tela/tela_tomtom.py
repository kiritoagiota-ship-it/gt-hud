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




import fluxo  # noqa: E402
import rota as rotas  # noqa: E402
import rota_tomtom  # noqa: E402
import transito  # noqa: E402

M = 1.0 / 111320.0
PEDIDOS = {"rota": 0, "conferir": 0, "fluxo": []}
DESTINO = {"nome": "Setor Sudoeste", "endereco": "", "lat": -16.7200, "lon": -49.2950}


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


def rota_falsa(chave, origem, destino, rumo=None, destino_nome="", baixar=None, elevacao_de=None):
    """A "TomTom" do teste: um caminho diferente do das outras rotas, 9 min, sem relevo."""
    PEDIDOS["rota"] += 1
    meio = ((origem[0] + destino[0]) / 2.0 + 900 * M, (origem[1] + destino[1]) / 2.0 + 900 * M)
    pontos = [tuple(origem)] + [(origem[0] + (meio[0] - origem[0]) * k / 20.0, origem[1] + (meio[1] - origem[1]) * k / 20.0)
                               for k in range(1, 21)]
    pontos += [(meio[0] + (destino[0] - meio[0]) * k / 20.0, meio[1] + (destino[1] - meio[1]) * k / 20.0)
               for k in range(1, 21)]
    r = rotas.Rota(pontos, [{"acao": "direita", "indice": 20, "texto": "Vire à direita", "ruas": "Rua do Teste",
                             "saida": None}], [], 540.0, destino_nome)
    r.perfil, r.nome_perfil, r.tempo_com_transito = "transito", "Pelo trânsito de agora", True
    return r


def conferir_falso(chave, rota, dist_feita, posicao, rumo=None, enviar=None):
    PEDIDOS["conferir"] += 1
    return {"atraso_s": 300.0, "falta_s": 900.0, "melhor": rota_falsa(chave, posicao, rota.pontos[-1]), "ganho_s": 240.0}


def tile_falso(self, chave, x, y):
    """Ruas "medidas" em volta de quem pedala: uma livre, uma lenta e uma parada."""
    PEDIDOS["fluxo"].append((x, y))
    lat, lon = app().posicao
    segmentos = [([(lat + 120 * M, lon - 300 * M + k * 60 * M) for k in range(11)], 0),
                 ([(lat - 100 * M, lon - 300 * M + k * 60 * M) for k in range(11)], 2),
                 ([(lat - 200 * M + k * 40 * M, lon + 150 * M) for k in range(11)], 3)]
    with self._trava:
        self._tiles[(x, y)] = (__import__("time").monotonic(), segmentos)
    return segmentos


rota_tomtom.pedir = rota_falsa
rota_tomtom.conferir = conferir_falso
fluxo.Fluxo.buscar_tile = tile_falso
transito.da_cidade = lambda chave, agora=None, baixar=None: []


def ligar(dt):
    app().ajustes["tomtom"] = "chave-de-mentira-para-o-teste"
    app().ajustes["rota_preferida"] = "rapida"
    app().atualizar_fluxo()


def ver_fluxo(dt):
    m = tela().mapa
    checar(len(PEDIDOS["fluxo"]) >= 1, "o mapa pediu as cores do trânsito da vista: %s" % PEDIDOS["fluxo"])
    checar(len(m._fluxo) == 3 * len(set(PEDIDOS["fluxo"])), "trechos coloridos no mapa: %d" % len(m._fluxo))
    checar(len(m._g_fluxo.children) >= 6, "uma malha por cor (livre, lento, parado)")
    foto("f0_ruas_coloridas")


def destino(dt):
    app().escolher_destino(dict(DESTINO))


def ver_previa(dt):
    a = app()
    nomes = [r.nome_perfil for r in a.rotas_previa]
    print("[TESTE] rotas:", [(r.nome_perfil, round(r.tempo_s)) for r in a.rotas_previa], flush=True)
    checar(PEDIDOS["rota"] == 1, "a rota pelo trânsito foi pedida uma vez: %d" % PEDIDOS["rota"])
    checar("Pelo trânsito de agora" in nomes and nomes[-1] == "Pelo trânsito de agora", "ela entra como opção, no fim: %s" % nomes)
    abas = [b.text.split(chr(10))[0] for b in tela().escolha.children[::-1] if hasattr(b, "text") and "min" in b.text]
    checar("Trânsito" in abas, "aba Trânsito no cartão: %s" % abas)
    viva = next(r for r in a.rotas_previa if r.perfil == "transito")
    a.escolher_rota_previa(viva)
    T["viva"] = viva
    Clock.schedule_once(lambda dt: foto("f1_rota_pelo_transito"), 1.2)


def navegar(dt):
    a = app()
    checar("9 min" in tela().lbl_resumo.text, "o tempo dela é o da TomTom (9 min): " + tela().lbl_resumo.text)
    a.iniciar_navegacao()
    checar(a.nav is not None and a.nav.rota is T["viva"], "navegando pela rota do trânsito")
    T["voo"] = tela().mapa._voo is not None
    Clock.schedule_once(lambda dt: foto("f2_mergulho"), 0.55)


def ver_nav(dt):
    a = app()
    m = tela().mapa
    checar(T.get("voo"), "ao iniciar, a câmera mergulha até a seta (voo)")
    checar(m._voo is None and m.seguindo and abs(m.zoom - 17.4) < 0.9, "o mergulho terminou seguindo a seta, zoom %.1f" % m.zoom)
    checar(PEDIDOS["conferir"] >= 1, "a TomTom conferiu o caminho em uso: %d" % PEDIDOS["conferir"])
    checar(a.nav.vivo is not None, "o tempo de chegada passou a usar o trânsito de agora")
    checar(a.rota_sugerida is not None, "caminho mais rápido guardado para o botão Rotas")
    checar(any("Encontrei um caminho" in f for f in FALAS), "avisou do caminho mais rápido por voz")
    checar("mais rápido" in tela().lbl_msg.text, "e na tela: " + tela().lbl_msg.text)
    checar("curva" in a.sons.tocados or "inicio" in a.sons.tocados or "pronto" in a.sons.tocados,
           "sons de aviso pedidos: %s" % a.sons.tocados[-8:])
    foto("f3_navegando")


T = {}


def fim(dt):
    app().ajustes["tomtom"] = ""   # a chave de mentira não fica para os outros testes
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(ligar, 7)
Clock.schedule_once(ver_fluxo, 9.5)
Clock.schedule_once(destino, 10)
Clock.schedule_once(ver_previa, 22)
Clock.schedule_once(navegar, 24)
Clock.schedule_once(ver_nav, 74)
Clock.schedule_once(fim, 76)
runpy.run_path("main.py", run_name="__main__")
