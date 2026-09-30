"""Ajustes: limite de velocidade, suavização, tela ligada e simulador."""
from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

import tema
from widgets.botao import BotaoHUD
from widgets.comuns import Cabecalho, Texto


class Linha(BoxLayout):
    """Título + explicação à esquerda, controle à direita."""

    def __init__(self, titulo, explicacao, controle, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(84))
        kw.setdefault("spacing", dp(10))
        super().__init__(**kw)
        textos = BoxLayout(orientation="vertical")
        textos.add_widget(Texto(text=titulo, font_size=tema.T_BOTAO, bold=True))
        textos.add_widget(Texto(text=explicacao, font_size=tema.T_ROTULO, color=tema.CIANO_FRACO))
        self.add_widget(textos)
        self.add_widget(controle)


class Seletor(BoxLayout):
    """[-] valor [+]"""

    def __init__(self, formato, ao_mudar, **kw):
        kw.setdefault("size_hint_x", None)
        kw.setdefault("width", dp(170))
        kw.setdefault("spacing", dp(6))
        kw.setdefault("padding", (0, dp(16)))
        super().__init__(**kw)
        self.formato = formato
        self.ao_mudar = ao_mudar
        self.add_widget(BotaoHUD(text="-", size_hint_x=None, width=dp(46),
                                 on_release=lambda *a: self.ao_mudar(-1)))
        self.lbl = Label(font_size=tema.T_BOTAO, bold=True, color=tema.BRANCO)
        self.add_widget(self.lbl)
        self.add_widget(BotaoHUD(text="+", size_hint_x=None, width=dp(46),
                                 on_release=lambda *a: self.ao_mudar(+1)))

    def mostrar(self, valor):
        self.lbl.text = self.formato % valor


class Alternar(BotaoHUD):
    def __init__(self, ao_mudar, **kw):
        kw.setdefault("size_hint_x", None)
        kw.setdefault("width", dp(130))
        super().__init__(**kw)
        self.ao_mudar = ao_mudar
        self.bind(on_release=lambda *a: self.ao_mudar(not self.destaque))

    def mostrar(self, ligado):
        self.destaque = bool(ligado)
        self.text = "Ligado" if ligado else "Desligado"


class TelaConfig(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        raiz = BoxLayout(orientation="vertical", padding=tema.MARGEM, spacing=dp(8))
        raiz.add_widget(Cabecalho("Ajustes", self._voltar))

        self.sel_limite = Seletor("%d km/h", self._mudar_limite)
        raiz.add_widget(Linha("Alerta de velocidade",
                              "O velocimetro fica laranja e pisca acima deste valor.",
                              self.sel_limite))

        self.sel_alfa = Seletor("%.1f", self._mudar_alfa)
        raiz.add_widget(Linha("Resposta do velocimetro",
                              "Menor: numero mais estavel. Maior: reage mais rapido.",
                              self.sel_alfa))

        self.alt_tela = Alternar(self._mudar_tela)
        raiz.add_widget(Linha("Manter tela ligada",
                              "Evita a tela apagar durante a viagem.",
                              self._centralizar(self.alt_tela)))

        self.alt_sim = Alternar(self._mudar_sim)
        raiz.add_widget(Linha("Modo simulador",
                              "Usa GPS falso para testar o app parado.",
                              self._centralizar(self.alt_sim)))

        raiz.add_widget(Widget())
        self.add_widget(raiz)

    @staticmethod
    def _centralizar(w):
        caixa = BoxLayout(size_hint_x=None, width=w.width, padding=(0, dp(16)))
        caixa.add_widget(w)
        return caixa

    def on_pre_enter(self, *a):
        aj = App.get_running_app().ajustes
        self.sel_limite.mostrar(aj["limite_kmh"])
        self.sel_alfa.mostrar(aj["alfa"])
        self.alt_tela.mostrar(aj["tela_ligada"])
        self.alt_sim.mostrar(aj["simulador"])

    def _mudar_limite(self, d):
        aj = App.get_running_app().ajustes
        aj["limite_kmh"] = max(10, min(60, aj["limite_kmh"] + d))
        self.sel_limite.mostrar(aj["limite_kmh"])

    def _mudar_alfa(self, d):
        app = App.get_running_app()
        novo = round(max(0.1, min(0.9, app.ajustes["alfa"] + d * 0.1)), 1)
        app.ajustes["alfa"] = novo
        app.filtro.alfa = novo
        self.sel_alfa.mostrar(novo)

    def _mudar_tela(self, ligado):
        app = App.get_running_app()
        app.ajustes["tela_ligada"] = ligado
        app.aplicar_tela_ligada()
        self.alt_tela.mostrar(ligado)

    def _mudar_sim(self, ligado):
        App.get_running_app().aplicar_simulador(ligado)
        self.alt_sim.mostrar(ligado)

    def _voltar(self):
        self.manager.current = "hud"
