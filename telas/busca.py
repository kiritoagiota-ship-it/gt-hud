"""Busca de destino: digita, toca em Buscar, escolhe o lugar. Sem texto,
mostra os destinos recentes."""
from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

import busca
import rede
import tema
from util import fmt_dist_nav
from widgets.botao import BotaoHUD
from widgets.comuns import Cabecalho, ItemViagem, Texto


class TelaBusca(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._buscando = False
        raiz = BoxLayout(orientation="vertical", padding=tema.MARGEM, spacing=dp(10))
        raiz.add_widget(Cabecalho("Para onde, senhor?", self._voltar))

        linha = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.campo = TextInput(
            hint_text="Endereco ou lugar", multiline=False, font_size=tema.T_BOTAO,
            background_normal="", background_active="", background_color=tema.PAINEL,
            foreground_color=tema.BRANCO, hint_text_color=tema.CIANO_FRACO,
            cursor_color=tema.CIANO, padding=(dp(12), dp(14)), write_tab=False)
        self.campo.bind(on_text_validate=lambda *a: self._buscar(),
                        text=lambda *a: self._texto_mudou())
        linha.add_widget(self.campo)
        linha.add_widget(BotaoHUD(text="Buscar", destaque=True, size_hint_x=None, width=dp(96),
                                  on_release=lambda *a: self._buscar()))
        raiz.add_widget(linha)

        self.lbl_status = Texto(text="", font_size=tema.T_ROTULO + 1, color=tema.CIANO_FRACO,
                                size_hint_y=None, height=dp(22))
        raiz.add_widget(self.lbl_status)
        rolagem = ScrollView(do_scroll_x=False, bar_color=tema.CIANO, bar_width=dp(3))
        self.lista = GridLayout(cols=1, size_hint_y=None, spacing=dp(6))
        self.lista.bind(minimum_height=self.lista.setter("height"))
        rolagem.add_widget(self.lista)
        raiz.add_widget(rolagem)
        self.add_widget(raiz)

    def on_pre_enter(self, *a):
        self.campo.text = ""
        self._mostrar_recentes()

    def on_enter(self, *a):
        self.campo.focus = True  # já abre o teclado

    def _texto_mudou(self):
        if not self.campo.text.strip() and not self._buscando:
            self._mostrar_recentes()

    def _mostrar_recentes(self):
        recentes = App.get_running_app().recentes
        self.lbl_status.text = "Recentes" if recentes else "Digite um endereco, bairro ou lugar."
        self._listar(recentes)

    def _listar(self, lugares):
        self.lista.clear_widgets()
        for lugar in lugares:
            detalhe = lugar.get("endereco") or ""
            if lugar.get("dist_m") is not None:
                detalhe = "%s  |  %s" % (fmt_dist_nav(lugar["dist_m"]), detalhe)
            item = ItemViagem(lugar["nome"], detalhe)
            item.bind(on_release=lambda w, l=lugar: self._escolher(l))
            self.lista.add_widget(item)

    def _buscar(self):
        texto = self.campo.text.strip()
        if len(texto) < 3 or self._buscando:
            return
        app = App.get_running_app()
        self._buscando = True
        self.lbl_status.text = "Buscando..."
        self.lista.clear_widgets()
        rede.em_segundo_plano(lambda: busca.buscar(texto, app.posicao),
                              self._resultados, self._falhou)

    def _resultados(self, lugares):
        self._buscando = False
        n = len(lugares)
        self.lbl_status.text = ("%d %s" % (n, "resultado" if n == 1 else "resultados")) if n else \
            "Nada encontrado. Tente com o bairro ou a cidade."
        self._listar(lugares)

    def _falhou(self, erro):
        self._buscando = False
        self.lbl_status.text = "Sem internet para buscar. Confira a conexao."

    def _escolher(self, lugar):
        self.campo.focus = False
        App.get_running_app().escolher_destino(lugar)

    def _voltar(self):
        self.campo.focus = False
        App.get_running_app().voltar()
