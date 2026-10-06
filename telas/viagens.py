"""Histórico de viagens."""
from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView

import tema
from util import fmt_data, fmt_dist, fmt_tempo
from widgets.comuns import Cabecalho, ItemViagem, Texto


class TelaViagens(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        raiz = BoxLayout(orientation="vertical", padding=tema.MARGEM, spacing=dp(12))
        raiz.add_widget(Cabecalho("Viagens", self._voltar))
        self.lbl_total = Texto(text="", font_size=tema.T_ROTULO + 1, color=tema.CIANO_FRACO,
                               size_hint_y=None, height=dp(22))
        raiz.add_widget(self.lbl_total)
        self.scroll = ScrollView(do_scroll_x=False, bar_color=tema.CIANO, bar_width=dp(3))
        self.lista = GridLayout(cols=1, size_hint_y=None, spacing=dp(6))
        self.lista.bind(minimum_height=self.lista.setter("height"))
        self.scroll.add_widget(self.lista)
        raiz.add_widget(self.scroll)
        self.add_widget(raiz)

    def on_pre_enter(self, *a):
        viagens = App.get_running_app().banco.listar_viagens()
        self.lista.clear_widgets()
        if not viagens:
            self.lbl_total.text = ""
            self.lista.add_widget(Texto(
                text="Nenhuma viagem gravada ainda.\n"
                     "Toda rota que você iniciar é gravada sozinha e aparece aqui.",
                font_size=tema.T_BOTAO, color=tema.CIANO_FRACO,
                size_hint_y=None, height=dp(90)))
            return
        total_m = sum(v["distancia_m"] or 0 for v in viagens)
        n = len(viagens)
        self.lbl_total.text = "%d %s   %s no total" % (n, "viagem" if n == 1 else "viagens",
                                                      fmt_dist(total_m))
        for v in viagens:
            numeros = "%s    %s    max %.0f km/h" % (
                fmt_dist(v["distancia_m"]), fmt_tempo(v["duracao_s"]), v["vel_max_kmh"] or 0)
            if v.get("destino"):   # a viagem é uma rota: o destino é o título
                item = ItemViagem("Para " + v["destino"], "%s    %s" % (fmt_data(v["inicio"]), numeros))
            else:
                item = ItemViagem(fmt_data(v["inicio"]), numeros)
            item.bind(on_release=lambda w, vid=v["id"]: self._abrir(vid))
            self.lista.add_widget(item)

    def _abrir(self, vid):
        self.manager.get_screen("detalhe").viagem_id = vid
        self.manager.current = "detalhe"

    def _voltar(self):
        App.get_running_app().voltar()
