"""Detalhe de uma viagem: trajeto, gráfico de velocidade e estatísticas."""
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import Screen

import tema
from util import fmt_data, fmt_dist, fmt_tempo, fmt_vel
from widgets.botao import BotaoHUD
from widgets.comuns import Bloco, Cabecalho, soltar
from widgets.grafico import GraficoVelocidade
from widgets.trajeto import MapaTrajeto


class TelaDetalhe(Screen):
    viagem_id = NumericProperty(0)

    def __init__(self, **kw):
        super().__init__(**kw)
        self._confirmando = False
        self._deitada = None
        self.raiz = BoxLayout(orientation="vertical", padding=tema.MARGEM, spacing=dp(10))
        self.cab = Cabecalho("", self._voltar)

        # abas: o mesmo espaço mostra o trajeto ou o gráfico de velocidade
        self.abas = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        self.aba_trajeto = BotaoHUD(text="Trajeto", font_size=tema.T_ROTULO + 2,
                                    on_release=lambda *a: self._mostrar(self.mapa))
        self.aba_vel = BotaoHUD(text="Velocidade", font_size=tema.T_ROTULO + 2,
                                on_release=lambda *a: self._mostrar(self.grafico))
        self.abas.add_widget(self.aba_trajeto)
        self.abas.add_widget(self.aba_vel)
        self.painel = BoxLayout()
        self.mapa = MapaTrajeto()
        self.grafico = GraficoVelocidade()
        self._mostrar(self.mapa)

        self.grade = GridLayout(cols=2, spacing=dp(8))
        self.b = {}
        for chave, rot in [("dist", "Distância"), ("dur", "Tempo total"),
                           ("mov", "Em movimento"), ("max", "Máxima (km/h)"),
                           ("med", "Média (km/h)"), ("pts", "Leituras de GPS")]:
            self.b[chave] = Bloco(rotulo=rot)
            self.grade.add_widget(self.b[chave])

        self.btn_apagar = BotaoHUD(text="Apagar viagem", cor=tema.VERMELHO,
                                   size_hint_y=None, height=dp(54),
                                   on_release=lambda *a: self._apagar())
        self.add_widget(self.raiz)
        self.bind(size=self._organizar)

    def _organizar(self, *a):
        """Em pé: tudo empilhado. Deitada: desenho à esquerda, números à direita."""
        deitada = self.width > self.height
        if deitada == self._deitada:
            return
        self._deitada = deitada
        soltar(self.cab, self.abas, self.painel, self.grade, self.btn_apagar)
        self.raiz.clear_widgets()
        self.raiz.add_widget(self.cab)
        if deitada:
            self.grade.size_hint_y = 1
            esq = BoxLayout(orientation="vertical", spacing=dp(8))
            esq.add_widget(self.abas)
            esq.add_widget(self.painel)
            dir_ = BoxLayout(orientation="vertical", spacing=dp(8))
            dir_.add_widget(self.grade)
            dir_.add_widget(self.btn_apagar)
            corpo = BoxLayout(spacing=dp(10))
            corpo.add_widget(esq)
            corpo.add_widget(dir_)
            self.raiz.add_widget(corpo)
        else:
            self.grade.size_hint_y = None
            self.grade.height = dp(252)
            for w in (self.abas, self.painel, self.grade, self.btn_apagar):
                self.raiz.add_widget(w)

    def _mostrar(self, desenho):
        self.painel.clear_widgets()
        self.painel.add_widget(desenho)
        self.aba_trajeto.destaque = desenho is self.mapa
        self.aba_vel.destaque = desenho is self.grafico

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        resumo, pontos = app.banco.obter_viagem(self.viagem_id)
        self._resetar_apagar()
        if not resumo:
            self._voltar()
            return
        self.cab.titulo.text = fmt_data(resumo["inicio"])
        limite = app.ajustes["limite_kmh"]
        self.mapa.limite = limite
        self.mapa.pontos = [(lat, lon, v) for (lat, lon, v, _) in pontos]
        self.grafico.limite = limite
        self.grafico.pontos = [(t, v) for (_, _, v, t) in pontos]
        self.b["dist"].valor = fmt_dist(resumo["distancia_m"])
        self.b["dur"].valor = fmt_tempo(resumo["duracao_s"])
        self.b["mov"].valor = fmt_tempo(resumo["tempo_mov_s"])
        self.b["max"].valor = fmt_vel(resumo["vel_max_kmh"])
        self.b["med"].valor = fmt_vel(resumo["vel_media_kmh"])
        self.b["pts"].valor = str(len(pontos))

    def _apagar(self):
        if not self._confirmando:
            self._confirmando = True
            self.btn_apagar.text = "Toque de novo para apagar"
            self.btn_apagar.destaque = True
            Clock.schedule_once(lambda dt: self._resetar_apagar(), 3)
            return
        App.get_running_app().banco.apagar_viagem(self.viagem_id)
        self.manager.current = "viagens"

    def _resetar_apagar(self):
        self._confirmando = False
        self.btn_apagar.text = "Apagar viagem"
        self.btn_apagar.destaque = False

    def _voltar(self):
        self.manager.current = "viagens"
