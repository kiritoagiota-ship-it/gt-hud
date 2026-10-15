"""Teste de TELA do GT-HUD (janela no 2º monitor). Rodar por
ferramentas/testes_tela/rodar_todos.py (que isola APPDATA/KIVY_HOME)."""
import os
import runpy
import sys
import math
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


def falar_falso(self, pedacos, prioridade=1, texto=None, nervosa=False):
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


import tema  # noqa: E402
import widgets.comuns as comuns  # noqa: E402
from widgets.botao import AFUNDA, mexer  # noqa: E402


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


def depois(segundos, funcao):
    Clock.schedule_once(lambda dt: funcao(), segundos)


def tirar(nome):
    Window.screenshot(name=os.path.join(FOTOS, nome + ".png"))


class ToqueFalso:
    def __init__(self, x, y, duplo=False):
        self.x, self.y, self.pos = x, y, (x, y)
        self.ud, self.time_start = {}, time.time()
        self.is_double_tap = duplo
        self.is_mouse_scrolling = False
        self.grab_current = None

    def grab(self, w):
        self.grab_current = w

    def ungrab(self, w):
        self.grab_current = None


def botao_e_janela(dt):
    t = tela()
    checar(t._entrou, "a folha de baixo subiu na abertura")
    checar(abs(mexer(t.barra_livre)[0].y) < 1.0, "... e terminou no lugar: %.1f" % mexer(t.barra_livre)[0].y)
    b = t.btn_mais
    b.state = "down"
    checar(abs(mexer(b)[1].x - (1.0 - AFUNDA)) < 0.001, "botão apertado encolhe: %.3f" % mexer(b)[1].x)
    b.state = "normal"
    depois(0.5, lambda: checar(abs(mexer(b)[1].x - 1.0) < 0.005, "... e volta ao tamanho: %.3f" % mexer(b)[1].x))
    j = comuns.escolher("Janela de teste", [("Uma opção", lambda: None), ("Fechar", None)], "Fecha encolhendo.")
    T["janela"] = j
    j.botoes[0].dispatch("on_release")
    checar(j.parent is None, "escolher uma opção fecha a janela na hora (sem atropelar o que vem depois)")
    j = comuns.escolher("Janela de teste", [("Uma opção", lambda: None), ("Fechar", None)], "Fecha encolhendo.")

    def fechar():
        j.dismiss()
        checar(j.parent is not None, "a janela não some de estalo ao fechar")
        depois(0.06, lambda: tirar("a0_janela_fechando"))
        depois(0.5, lambda: checar(j.parent is None, "... e some de vez em seguida"))
    depois(0.6, fechar)


def aviso_e_bateria(dt):
    t = tela()
    t.mensagem("Aviso de teste", segundos=0.4)
    depois(0.1, lambda: checar(0.0 < t.lbl_msg.opacity <= 1.0 and mexer(t.lbl_msg)[0].y < 0,
                               "o aviso entra subindo: y=%.1f" % mexer(t.lbl_msg)[0].y))
    depois(0.55, lambda: checar(t.lbl_msg.text != "" and t.lbl_msg.opacity < 1.0,
                                "o aviso se apaga antes de sair: %.2f" % t.lbl_msg.opacity))
    depois(1.1, lambda: checar(t.lbl_msg.text == "", "... e o texto sai"))
    t.btn_bateria.pulsar()
    checar(mexer(t.btn_bateria)[1].x > 1.05, "o botão da bateria estufa ao confirmar: %.2f" % mexer(t.btn_bateria)[1].x)
    depois(0.8, lambda: checar(abs(mexer(t.btn_bateria)[1].x - 1.0) < 0.01, "... e volta"))


def toque_duplo(dt):
    m = tela().mapa
    m.seguindo = False
    m._aplicar()
    z0 = m.zoom
    onde = (m.x + m.width * 0.7, m.y + m.height * 0.6)
    antes = m._local_para_geo(*m._tela_para_local(*onde))
    m.on_touch_down(ToqueFalso(onde[0], onde[1], duplo=True))
    checar(abs(m.zoom - z0) < 0.01, "o zoom do toque duplo não pula de uma vez")
    depois(0.12, lambda: checar(0.05 < m.zoom - z0 < 0.98, "... desliza: +%.2f" % (m.zoom - z0)))

    def no_fim():
        checar(abs(m.zoom - z0 - 1.0) < 0.01, "... e chega a um nível a mais: +%.2f" % (m.zoom - z0))
        agora = m._local_para_geo(*m._tela_para_local(*onde))
        erro_m = math.hypot(agora[0] - antes[0], agora[1] - antes[1]) * 111320.0
        checar(erro_m < 3.0, "o ponto tocado ficou parado debaixo do dedo: %.1f m" % erro_m)
    depois(0.7, no_fim)


def pino(dt):
    m = tela().mapa
    lat, lon = m.centro
    m.definir_destino((lat + 0.0006, lon), cair=True)
    checar(not m._dest_pousou, "o pino começa no ar")
    depois(0.2, lambda: tirar("a1_pino_caindo"))
    depois(0.55, lambda: checar(m._dest_pousou and m._onda_toque is not None, "bateu no chão e soltou a onda"))
    depois(1.3, lambda: checar(m._dest_t0 is None, "o pino assentou"))
    depois(1.4, lambda: m.definir_destino(None))


def chegada(dt):
    t = tela()
    t.mostrar_resumo("Você chegou!", "Destino de teste", {"distancia_m": 12400.0, "duracao_s": 1500.0,
                                                           "vel_media_kmh": 38.0, "vel_max_kmh": 49.0})
    checar(t.res_max.valor.text == "0", "os números começam em zero: %r" % t.res_max.valor.text)
    checar(mexer(t.card_resumo)[1].x < 0.9, "o cartão entra pequeno")
    depois(0.25, lambda: tirar("a2_chegada_contando"))

    def no_fim():
        checar(t.res_max.valor.text == "49" and t.res_media.valor.text == "38" and "12" in t.res_dist.valor.text,
               "... e chegam ao valor: %s, média %s, máx %s" % (t.res_dist.valor.text, t.res_media.valor.text,
                                                              t.res_max.valor.text))
        checar(abs(mexer(t.card_resumo)[1].x - 1.0) < 0.01, "o cartão ficou do tamanho certo")
        t._fechar_resumo()
    depois(1.3, no_fim)


def curva(dt):
    t = tela()
    t._pulsar_curva(True)
    checar(t._pulso_curva is not None, "perto da curva a faixa pulsa")
    depois(0.25, lambda: checar(list(t.faixa.cor_borda) != list(tema.CIANO), "a borda está clareando"))

    def parar():
        t._pulsar_curva(False)
        checar(t._pulso_curva is None and list(t.faixa.cor_borda) == list(tema.CIANO), "longe da curva, para")
    depois(0.9, parar)


def telas(dt):
    a = app()
    a.abrir("config")
    checar(getattr(a, "_capa_tema", None) is None or a._capa_tema.parent is None, "do mapa para os Ajustes: sem foto do mapa")

    def voltar():
        a.voltar()
        capa = getattr(a, "_capa_tema", None)
        checar(a.sm.current == "mapa" and capa is not None and capa.parent is not None,
               "ao voltar, a tela dos Ajustes se dissolve por cima do mapa")
        depois(0.07, lambda: tirar("a3_tela_saindo"))
        depois(0.6, lambda: checar(capa.parent is None, "... e some"))
    depois(0.6, voltar)


def pontilhado(dt):
    m = tela().mapa
    lat, lon = m.centro
    m.definir_rota([(lat - 0.0012 + k * 0.0002, lon) for k in range(7)])
    m.definir_destino((lat + 0.0004, lon + 0.0005))        # o lugar fica ~70 m para dentro da quadra
    tracos = [l for l, larg in m._larg_rota if abs(larg - dp(2.2)) < 0.01]
    checar(len(tracos) >= 4, "linha pontilhada do fim da rota ate o pino: %d tracos" % len(tracos))
    depois(0.3, lambda: tirar("a4_pontilhado"))

    # navegando: mexeu no zoom, o zoom automático da rota espera (antes desfazia em menos de 1 s)
    m.modo_navegacao(True)
    m.seguindo = True
    m.mudar_zoom(1)
    pedido = m._alvo_zoom
    m.mostrar_eu(lat, lon, 0.0, 5.0, 40.0)
    checar(m._alvo_zoom == pedido, "navegando, o zoom manual vale: %s" % m._alvo_zoom)
    m._zoom_manual_ate = 0.0
    m.mostrar_eu(lat, lon, 0.0, 5.0, 40.0)
    checar(m._alvo_zoom != pedido, "... e depois do prazo o automático volta: %s" % m._alvo_zoom)
    m.modo_navegacao(False)
    m.seguindo = False

    def limpar():
        m.definir_destino((lat + 0.00003, lon))             # o lugar na beira da rua: sem pontilhado
        checar(not [l for l, larg in m._larg_rota if abs(larg - dp(2.2)) < 0.01], "lugar na rua: sem pontilhado")
        m.definir_rota([])
        m.definir_destino(None)
    depois(0.7, limpar)


def viagens(dt):
    """A lista de viagens entra aos poucos (não trava ao abrir) e não é refeita se nada mudou."""
    a = app()
    banco = a.banco
    criadas = []
    for k in range(30):       # 30 viagens de mentira (apagadas no fim)
        criadas.append(banco.salvar_viagem({"inicio": 1000.0 + k, "fim": 1600.0 + k, "distancia_m": 1500.0 + k,
                                            "duracao_s": 600.0, "tempo_mov_s": 500.0, "vel_max_kmh": 40.0,
                                            "vel_media_kmh": 20.0, "destino": "Teste %d" % k}, []))
    total = len(banco.listar_viagens())
    t0 = time.perf_counter()
    a.abrir("viagens")
    gasto = (time.perf_counter() - t0) * 1000
    tv = a.sm.get_screen("viagens")
    logo = len(tv.lista.children)
    checar(logo <= 10 < total, "ao abrir entram so as primeiras: %d de %d (%.0f ms)" % (logo, total, gasto))

    def completa():
        itens = [w for w in tv.lista.children if type(w).__name__ == "ItemViagem"]
        dias = [w.text for w in tv.lista.children if type(w).__name__ == "Texto"]
        checar(len(itens) == total, "... e o resto entra aos poucos: %d de %d" % (len(itens), total))
        checar(len(dias) >= 1 and all(" em " in d for d in dias), "cada dia tem o titulo com o total dele: %s" % dias[-2:])
        checar(tv.totais["total"].valor.text.endswith("km") and "viagens" in tv.totais["total"].legenda.text,
               "resumo no topo: %s (%s)" % (tv.totais["total"].valor.text, tv.totais["total"].legenda.text))
        primeiro = tv.lista.children[-1]
        a.voltar()
        a.abrir("viagens")
        checar(tv.lista.children[-1] is primeiro,
               "abrir de novo sem nada mudar nao refaz a lista")
        banco.apagar_viagem(criadas[-1])
        a.voltar()
        a.abrir("viagens")
        checar(tv.lista.children[-1] is not primeiro, "apagou uma viagem: a lista e refeita")
        a.voltar()
        for vid in criadas[:-1]:
            banco.apagar_viagem(vid)
    depois(0.35, lambda: tirar("a5_viagens"))
    t_fim = time.time() + 6

    def esperar(dt):       # (a lista entra aos poucos: espera acabar, com um teto)
        if tv._ev_resto is not None and time.time() < t_fim:
            return True
        completa()
        return False
    Clock.schedule_interval(esperar, 0.2)


def lugares(dt):
    """Os lugares (mercado, farmacia...) que ja estao na tela FICAM enquanto o mapa anda ou o zoom
    se afasta um pouco (o dono, 13/10/2026: "qualquer coisinha o lugar some do mapa")."""
    m = tela().mapa
    m.seguindo = False
    m.centro = (-16.6865, -49.2648)     # Setor Oeste: cheio de comercio
    m.zoom = 17.7
    m._aplicar()

    def base(r):
        return r.info.get("tipo") == "poi" and "conf" in r.info

    def na_tela(info):
        x, y = m._local_para_tela(info["x"], info["y"])
        if not (m.x + dp(40) < x < m.right - dp(40) and m.y + dp(40) < y < m.top - dp(40)):
            return False
        # (debaixo de um botao ou painel ele sai mesmo: nao conta como sumico)
        return not any(o[0] - dp(20) < x < o[2] + dp(20) and o[1] - dp(20) < y < o[3] + dp(20)
                       for o in m.areas_cobertas)

    def medir():
        m._escolher_rotulos()
        antes = [r.info for r in m._rotulos if base(r)]
        checar(len(antes) >= 5, "lugares da base na tela: %d" % len(antes))
        sumiram = 0
        for passo in range(8):           # o mapa anda aos poucos, como arrastando com o dedo
            m._arrastar(-dp(22), dp(14))
            m._aplicar()
            m._escolher_rotulos()
            agora = [r.info for r in m._rotulos if base(r)]
            sumiram += sum(1 for i in antes if na_tela(i) and not any(i is j for j in agora))
            antes = [i for i in antes if any(i is j for j in agora)] + [j for j in agora
                                                                        if not any(j is i for i in antes)]
        T["sumiram"] = sumiram
        checar(sumiram <= 2, "arrastando o mapa, lugar que esta a vista nao some: %d sumicos em 8 passos" % sumiram)
        m._escolher_rotulos()
        antes = [r.info for r in m._rotulos if base(r)]
        m.zoom = 16.2                    # abaixo de onde os lugares entram (16,5): antes sumiam todos
        m._aplicar()
        m._escolher_rotulos()
        agora = [r.info for r in m._rotulos if base(r)]
        ficaram = sum(1 for i in antes if any(i is j for j in agora))
        T["ficaram"] = (ficaram, len(antes))
        checar(ficaram >= 0.35 * len(antes) and ficaram >= 2,
               "afastando o zoom, os lugares que estavam na tela ficam: %d de %d" % (ficaram, len(antes)))
        if agora:   # o toque pega a ate ~30 dp do emblema
            x, y = m._local_para_tela(agora[0]["x"], agora[0]["y"])
            checar(m.lugar_em(x + dp(20), y + dp(20)) is not None, "tocar perto do emblema (28 dp) acha o lugar")
        m.zoom = 15.0                    # bem longe: ai sim saem
        m._aplicar()
        m._escolher_rotulos()
        checar(not [r for r in m._rotulos if base(r)], "com o zoom bem afastado, os lugares saem")
        m.zoom = 16.8
        m.seguindo = True
    depois(1.6, medir)


T = {}


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(botao_e_janela, 7)
Clock.schedule_once(aviso_e_bateria, 8.6)
Clock.schedule_once(toque_duplo, 10.2)
Clock.schedule_once(pino, 11.4)
Clock.schedule_once(chegada, 13.2)
Clock.schedule_once(curva, 15)
Clock.schedule_once(pontilhado, 16.4)
Clock.schedule_once(telas, 17.8)
Clock.schedule_once(viagens, 19.6)
Clock.schedule_once(lugares, 24)
Clock.schedule_once(fim, 27)
runpy.run_path("main.py", run_name="__main__")
