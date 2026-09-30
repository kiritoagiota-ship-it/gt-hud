"""Tela de inicialização: sequência de 'boot' enquanto o GPS acha sinal."""
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
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
    "Velocimetro .................. ok",
]


class TelaBoot(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._saiu = False
        raiz = BoxLayout(orientation="vertical", padding=dp(28), spacing=dp(10))

        raiz.add_widget(Widget(size_hint_y=0.6))
        self.titulo = Label(text="GT-HUD", font_size=dp(58), bold=True, color=tema.CIANO,
                            size_hint_y=None, height=dp(80))
        raiz.add_widget(self.titulo)
        raiz.add_widget(Label(text="Ouxi GT20", font_size=tema.T_BOTAO,
                              color=tema.CIANO_FRACO, size_hint_y=None, height=dp(24)))
        raiz.add_widget(Widget(size_hint_y=0.25))

        self.log = Texto(text="", font_size=tema.T_ROTULO + 1, color=tema.CIANO_FRACO,
                         valign="top", size_hint_y=None, height=dp(110))
        raiz.add_widget(self.log)
        self.status = Texto(text="", font_size=tema.T_BOTAO, bold=True, color=tema.BRANCO,
                            size_hint_y=None, height=dp(56))
        raiz.add_widget(self.status)
        raiz.add_widget(Widget(size_hint_y=0.4))

        self.botoes = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(12))
        raiz.add_widget(self.botoes)
        self.add_widget(raiz)

        self._linha = 0
        self._ev_log = None
        self._mostrar_botoes_padrao()

    # --- sequência de boot -------------------------------------------------
    def on_enter(self, *a):
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
        if app.gps.modo == "SIM":
            self.status.text = "Modo simulador ativo"
        else:
            self.status.text = "Procurando satelites...\nFique em area aberta."
        self.status.color = tema.BRANCO
        self._mostrar_botoes_padrao()

    def permissao_negada(self):
        self.status.text = ("Sem permissao de localizacao precisa.\n"
                            "Toque em Tentar de novo e escolha 'Precisa'.")
        self.status.color = tema.VERMELHO
        self.botoes.clear_widgets()
        self.botoes.add_widget(BotaoHUD(text="Tentar de novo", destaque=True,
                                        on_release=lambda *a: App.get_running_app().solicitar_gps()))
        self.botoes.add_widget(BotaoHUD(text="Usar simulador",
                                        on_release=lambda *a: App.get_running_app().aplicar_simulador(True)))

    def _mostrar_botoes_padrao(self):
        self.botoes.clear_widgets()
        self.botoes.add_widget(BotaoHUD(text="Ir para o painel",
                                        on_release=lambda *a: self._ir_para_hud()))

    # --- primeira leitura boa ----------------------------------------------
    def _ao_ler(self, vel):
        if vel is None or self._saiu or self.manager.current != self.name:
            return
        app = App.get_running_app()
        prec = app.precisao or 0
        self.status.text = "Sinal adquirido: precisao %d m" % prec
        self.status.color = tema.VERDE
        Clock.schedule_once(lambda dt: self._ir_para_hud(), 0.9)
        self._saiu = True

    def _ir_para_hud(self):
        if self.manager.current == self.name:
            self.manager.current = "hud"
