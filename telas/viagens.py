"""Histórico de viagens: o resumo (semana, mês, total) e a lista, separada por dia."""
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView

import tema
from util import fmt_dist, fmt_tempo
from widgets.comuns import Cabecalho, ItemViagem, PainelHUD, Texto

PRIMEIRAS = 10      # as linhas que entram na hora (enchem a tela)
POR_QUADRO = 6      # ... e as outras vão entrando aos poucos, estas por quadro
DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
DIA_S = 86400.0


def _meia_noite(ts):
    """O começo (00:00, hora do celular) do dia de `ts`."""
    try:
        t = time.localtime(ts)
        return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
    except (OverflowError, ValueError, OSError):
        # data impossível (viagem gravada com o relógio zerado): não derruba a tela
        return ts - ts % DIA_S


def _km(metros):
    """Distância curta para os resumos: "850 m" ou "12,4 km"."""
    if metros < 1000:
        return "%d m" % metros
    return ("%.1f km" % (metros / 1000.0)).replace(".", ",")


def resumo(viagens, agora=None):
    """Os totais para o topo da tela: {"semana", "mes", "total"} -> (metros, quantas viagens).
    A semana começa na segunda; o mês, no dia 1."""
    agora = time.time() if agora is None else agora
    t = time.localtime(agora)
    # (do meio-dia de hoje para trás: uma troca de horário no meio da semana não erra o dia)
    inicio_semana = _meia_noite(_meia_noite(agora) + DIA_S / 2 - t.tm_wday * DIA_S)
    inicio_mes = time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, -1))
    somas = {"semana": [0.0, 0], "mes": [0.0, 0], "total": [0.0, 0]}
    for v in viagens:
        m, quando = v["distancia_m"] or 0, v["inicio"] or 0
        for chave, desde in (("semana", inicio_semana), ("mes", inicio_mes), ("total", None)):
            if desde is None or quando >= desde:
                somas[chave][0] += m
                somas[chave][1] += 1
    return {k: tuple(v) for k, v in somas.items()}


def nome_do_dia(ts, agora=None):
    """"Hoje", "Ontem" ou "seg, 12/10" (com o ano, se não for o de agora)."""
    agora = time.time() if agora is None else agora
    dias = round((_meia_noite(agora) - _meia_noite(ts)) / DIA_S)
    if dias == 0:
        return "Hoje"
    if dias == 1:
        return "Ontem"
    t = time.localtime(ts)
    texto = "%s, %02d/%02d" % (DIAS[t.tm_wday], t.tm_mday, t.tm_mon)
    return texto if t.tm_year == time.localtime(agora).tm_year else texto + "/%d" % t.tm_year


def linhas(viagens, agora=None):
    """A lista da tela, na ordem: ("dia", título do dia) e ("viagem", v). As viagens vêm da
    mais nova para a mais velha; cada dia ganha um título com o total dele."""
    saida, do_dia, dia_atual = [], [], None

    def fechar():
        if do_dia:
            total = sum(v["distancia_m"] or 0 for v in do_dia)
            n = len(do_dia)
            saida.append(("dia", "%s  ·  %s em %d %s" % (nome_do_dia(do_dia[0]["inicio"] or 0, agora), _km(total), n,
                                                           "viagem" if n == 1 else "viagens")))
            saida.extend(("viagem", v) for v in do_dia)
    for v in viagens:
        dia = _meia_noite(v["inicio"] or 0)
        if dia != dia_atual:
            fechar()
            do_dia, dia_atual = [], dia
        do_dia.append(v)
    fechar()
    return saida


class _Total(BoxLayout):
    """Um número do resumo: "37,2 km" grande, com "semana · 8" (viagens) embaixo."""

    def __init__(self, rotulo, **kw):
        kw.setdefault("orientation", "vertical")
        super().__init__(**kw)
        self._rotulo = rotulo
        self.valor = Texto(text="-", font_size=sp(19), bold=True, halign="center", shorten=True, max_lines=1)
        self.legenda = Texto(text=rotulo, font_size=tema.T_ROTULO, color=tema.CIANO_FRACO, halign="center",
                             size_hint_y=0.7, shorten=True, max_lines=1)
        self.add_widget(self.valor)
        self.add_widget(self.legenda)

    def mostrar(self, metros, viagens):
        self.valor.text = _km(metros)
        self.legenda.text = "%s · %d %s" % (self._rotulo, viagens, "viagem" if viagens == 1 else "viagens")


class TelaViagens(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._montada = None     # a lista que está montada (para não refazer igual)
        self._ev_resto = None
        raiz = BoxLayout(orientation="vertical", padding=tema.MARGEM, spacing=dp(10))
        raiz.add_widget(Cabecalho("Viagens", self._voltar))
        # o resumo: esta semana, este mês e tudo (pedido do dono, 13/10/2026: a tela era uma lista crua)
        self.painel = PainelHUD(size_hint_y=None, height=dp(66), padding=(dp(6), dp(6)))
        self.totais = {"semana": _Total("semana"), "mes": _Total("mês"), "total": _Total("total")}
        for chave in ("semana", "mes", "total"):
            self.painel.add_widget(self.totais[chave])
        raiz.add_widget(self.painel)
        self.scroll = ScrollView(do_scroll_x=False, bar_color=tema.CIANO, bar_width=dp(3))
        self.lista = GridLayout(cols=1, size_hint_y=None, spacing=dp(6))
        self.lista.bind(minimum_height=self.lista.setter("height"))
        self.scroll.add_widget(self.lista)
        raiz.add_widget(self.scroll)
        self.add_widget(raiz)

    def on_pre_enter(self, *a):
        viagens = App.get_running_app().banco.listar_viagens()
        for chave, (metros, quantas) in resumo(viagens).items():
            self.totais[chave].mostrar(metros, quantas)
        # Montar a lista INTEIRA de uma vez travava a tela ao abrir (medido em 12/10/2026: 110
        # viagens = 240 ms no PC, mais de 1 s num celular, e piorando a cada viagem nova).
        # Agora: nada mudou desde a última vez? Fica como está. Mudou: as primeiras entram na
        # hora e o resto vai entrando aos poucos, sem ninguém perceber.
        assinatura = [(v["id"], v.get("destino"), v["distancia_m"]) for v in viagens] + [_meia_noite(time.time())]
        if assinatura == self._montada:
            return
        self._montada = assinatura
        self._parar_resto()
        self.lista.clear_widgets()
        if not viagens:
            self.lista.add_widget(Texto(
                text="Nenhuma viagem gravada ainda.\n"
                     "Toda rota que você iniciar é gravada sozinha e aparece aqui.",
                font_size=tema.T_BOTAO, color=tema.CIANO_FRACO,
                size_hint_y=None, height=dp(90)))
            return
        todas = linhas(viagens)
        for linha in todas[:PRIMEIRAS]:
            self._por_linha(linha)
        resto = todas[PRIMEIRAS:]
        if resto:
            def mais(dt):
                for linha in resto[:POR_QUADRO]:
                    self._por_linha(linha)
                del resto[:POR_QUADRO]
                if not resto:
                    self._ev_resto = None
                    return False
            self._ev_resto = Clock.schedule_interval(mais, 0)

    def _parar_resto(self):
        if self._ev_resto is not None:
            self._ev_resto.cancel()
            self._ev_resto = None

    def _por_linha(self, linha):
        tipo, v = linha
        if tipo == "dia":     # o título do dia, com o total dele
            self.lista.add_widget(Texto(text=v, font_size=tema.T_ROTULO + 1, bold=True, color=tema.CIANO,
                                        size_hint_y=None, height=dp(30), valign="bottom"))
            return
        hora = time.strftime("%H:%M", time.localtime(v["inicio"] or 0))
        numeros = "%s    %s    max %.0f km/h" % (
            fmt_dist(v["distancia_m"]), fmt_tempo(v["duracao_s"]), v["vel_max_kmh"] or 0)
        if v.get("destino"):   # a viagem é uma rota: o destino é o título
            item = ItemViagem("Para " + v["destino"], "%s    %s" % (hora, numeros))
        else:
            item = ItemViagem("Às " + hora, numeros)
        item.bind(on_release=lambda w, vid=v["id"]: self._abrir(vid))
        self.lista.add_widget(item)

    def _abrir(self, vid):
        self.manager.get_screen("detalhe").viagem_id = vid
        self.manager.current = "detalhe"

    def _voltar(self):
        App.get_running_app().voltar()
