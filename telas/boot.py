"""Tela de inicialização: sequência de 'boot' enquanto o GPS acha sinal."""
from kivy.app import App
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Line
from kivy.metrics import dp
from kivy.properties import NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

import tema
from widgets.botao import BotaoHUD
from widgets.comuns import Texto

LINHAS = [
    "Nucleo do sistema ............ ok",
    "Banco de viagens ............. ok",
    "Velocímetro .................. ok",
]


class RiscoBoot(Widget):
    """Risco de HUD embaixo do nome: abre do centro para os lados ao ligar."""
    abertura = NumericProperty(0.0)

    def __init__(self, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(10))
        super().__init__(**kw)
        self.bind(pos=self._d, size=self._d, abertura=self._d)

    def abrir(self):
        Animation.cancel_all(self, "abertura")
        self.abertura = 0.0
        Animation(abertura=1.0, d=0.9, t="out_cubic").start(self)

    def _d(self, *a):
        self.canvas.clear()
        meia = min(self.width * 0.42, dp(150)) * self.abertura
        if meia <= 0:
            return
        cx, cy = self.center_x, self.center_y
        with self.canvas:
            Color(*tema.com_alfa(tema.CIANO, 0.18))
            Line(points=[cx - meia, cy, cx + meia, cy], width=dp(3.2))
            Color(*tema.CIANO)
            Line(points=[cx - meia, cy, cx + meia, cy], width=dp(1.3))
            for lado in (-1, 1):   # marcas nas pontas
                x = cx + lado * meia
                Line(points=[x, cy - dp(4), x, cy + dp(4)], width=dp(1.3))


class TelaBoot(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._saiu = False
        # em pé: marca em cima e informações embaixo; deitada: lado a lado
        self.raiz = BoxLayout(padding=dp(28), spacing=dp(10))

        self.marca = BoxLayout(orientation="vertical", spacing=dp(10))
        self._esp_cima = Widget(size_hint_y=0.6)
        self.marca.add_widget(self._esp_cima)
        self.titulo = Label(text="GT-HUD", font_size=dp(58), bold=True, color=tema.CIANO,
                            size_hint_y=None, height=dp(80))
        self.marca.add_widget(self.titulo)
        self.risco = RiscoBoot()
        self.marca.add_widget(self.risco)
        self.marca.add_widget(Label(text="Ouxi GT20", font_size=tema.T_BOTAO,
                                    color=tema.CIANO_FRACO, size_hint_y=None, height=dp(24)))
        self._esp_baixo = Widget(size_hint_y=0.25)
        self.marca.add_widget(self._esp_baixo)

        self.info = BoxLayout(orientation="vertical", spacing=dp(10))
        self.log = Texto(text="", font_size=tema.T_ROTULO + 1, color=tema.CIANO_FRACO,
                         valign="top", size_hint_y=None, height=dp(110))
        self.info.add_widget(self.log)
        self.status = Texto(text="", font_size=tema.T_BOTAO, bold=True, color=tema.BRANCO,
                            size_hint_y=None, height=dp(80))  # até 3 linhas
        self.info.add_widget(self.status)
        self.info.add_widget(Widget(size_hint_y=0.4))
        self.botoes = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(12))
        self.info.add_widget(self.botoes)

        self.raiz.add_widget(self.marca)
        self.raiz.add_widget(self.info)
        self.add_widget(self.raiz)
        self.bind(size=self._organizar)

        self._linha = 0
        self._ev_log = None
        self._buscando = False
        self._ev_busca = None
        self._negacoes = 0
        self._mostrar_botoes_padrao()

    def _organizar(self, *a):
        deitada = self.width > self.height
        self.raiz.orientation = "horizontal" if deitada else "vertical"
        # deitada, o nome fica no meio da altura; em pé, um pouco acima
        self._esp_cima.size_hint_y = 0.5 if deitada else 0.6
        self._esp_baixo.size_hint_y = 0.5 if deitada else 0.25

    # --- sequência de boot -------------------------------------------------
    def on_enter(self, *a):
        self.titulo.opacity = 0.0
        Animation(opacity=1.0, d=0.6, t="out_quad").start(self.titulo)
        self.risco.abrir()
        if not getattr(self, "_ouvindo", False):
            App.get_running_app().ouvir(self._ao_ler)
            self._ouvindo = True
        self.titulo.opacity = 0
        Clock.schedule_once(lambda dt: setattr(self.titulo, "opacity", 1), 0.15)
        self._linha = 0
        self.log.text = ""
        self._ev_log = Clock.schedule_interval(self._proxima_linha, 0.35)

    def _proxima_linha(self, dt):
        if self._linha >= len(LINHAS):
            return False
        self.log.text += LINHAS[self._linha] + "\n"
        self._linha += 1

    # --- chamados pelo app -------------------------------------------------
    def aguardando_sinal(self):
        app = App.get_running_app()
        self._buscando = app.gps.modo != "SIM"
        self.status.color = tema.BRANCO
        if self._buscando:
            self._atualizar_busca()
            if self._ev_busca is None:
                self._ev_busca = Clock.schedule_interval(self._atualizar_busca, 1.0)
        else:
            self.status.text = "Modo simulador ativo"
        self._mostrar_botoes_padrao()

    def _atualizar_busca(self, *a):
        """Enquanto procura, mostra quantos satélites o GPS já está vendo."""
        if self._saiu or not self._buscando or self.manager.current != self.name:
            self._ev_busca = None
            return False
        app = App.get_running_app()
        sat = app.gps.satelites()
        if app.sinal_fraco():
            linha = "Sinal fraco (%d m), melhorando..." % (app.precisao_ultima or 0)
        elif sat and sat[0]:
            linha = "Procurando satélites... %d vistos, %d em uso" % sat
        else:
            linha = "Procurando satélites..."
        self.status.text = linha + "\nFique em área aberta."

    def permissao_negada(self):
        self._buscando = False
        self._negacoes += 1
        if self._negacoes == 1:
            self.status.text = ("Sem permissão de localização precisa.\n"
                                "Toque em Tentar de novo e escolha 'Precisa'.")
        else:
            # negada 2x, o Android para de perguntar: só pelas configurações
            self.status.text = ("Libere a localização em Configurações >\n"
                                "Apps > GT-HUD > Permissões > Localização,\n"
                                "escolha 'Precisa' e toque em Tentar de novo.")
        self.status.color = tema.VERMELHO
        self.botoes.clear_widgets()
        self.botoes.add_widget(BotaoHUD(text="Tentar de novo", destaque=True,
                                        on_release=lambda *a: App.get_running_app().solicitar_gps()))
        self.botoes.add_widget(BotaoHUD(text="Usar simulador",
                                        on_release=lambda *a: App.get_running_app().aplicar_simulador(True)))

    def _mostrar_botoes_padrao(self):
        self.botoes.clear_widgets()
        self.botoes.add_widget(BotaoHUD(text="Ir para o mapa",
                                        on_release=lambda *a: self._ir_para_mapa()))

    # --- primeira leitura boa ----------------------------------------------
    def _ao_ler(self, vel):
        if vel is None or self._saiu or self.manager.current != self.name:
            return
        app = App.get_running_app()
        prec = app.precisao or 0
        self.status.text = "Sinal adquirido: precisão %d m" % prec
        self.status.color = tema.VERDE
        Clock.schedule_once(lambda dt: self._ir_para_mapa(), 0.9)
        self._saiu = True

    def _ir_para_mapa(self):
        if self.manager.current == self.name:
            self.manager.current = "mapa"
