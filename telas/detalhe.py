"""Detalhe de uma viagem: gráfico de velocidade e estatísticas."""
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
from widgets.comuns import Bloco, Cabecalho
from widgets.grafico import GraficoVelocidade


class TelaDetalhe(Screen):
    viagem_id = NumericProperty(0)

    def __init__(self, **kw):
        super().__init__(**kw)
        self._confirmando = False
        raiz = BoxLayout(orientation="vertical", padding=tema.MARGEM, spacing=dp(10))
        self.cab = Cabecalho("", self._voltar)
        raiz.add_widget(self.cab)

        self.grafico = GraficoVelocidade(size_hint_y=0.8)
        raiz.add_widget(self.grafico)

        grade = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(252))
        self.b = {}
        for chave, rot in [("dist", "Distancia"), ("dur", "Tempo total"),
                           ("mov", "Em movimento"), ("max", "Maxima (km/h)"),
                           ("med", "Media (km/h)"), ("pts", "Leituras de GPS")]:
            self.b[chave] = Bloco(rotulo=rot)
            grade.add_widget(self.b[chave])
        raiz.add_widget(grade)

        self.btn_apagar = BotaoHUD(text="Apagar viagem", cor=tema.VERMELHO,
                                   size_hint_y=None, height=dp(54),
                                   on_release=lambda *a: self._apagar())
        raiz.add_widget(self.btn_apagar)
        self.add_widget(raiz)

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        resumo, pontos = app.banco.obter_viagem(self.viagem_id)
        self._resetar_apagar()
        if not resumo:
            self._voltar()
            return
        self.cab.titulo.text = fmt_data(resumo["inicio"])
        self.grafico.limite = app.ajustes["limite_kmh"]
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
