"""Ajustes: voz, subidas e giro do mapa (navegação), alerta de velocidade,
vibração, pausa automática, orientação, tela ligada, suavização e simulador."""
import json
import os

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView

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


def _versao():
    """Número gravado pelo build do GitHub (1.0.N); no PC não existe."""
    try:
        with open(os.path.join(App.get_running_app().directory, "versao.json")) as f:
            return json.load(f)["versao"]
    except (OSError, ValueError, KeyError):
        return "de teste (PC)"


class TelaConfig(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        raiz = BoxLayout(orientation="vertical", padding=tema.MARGEM, spacing=dp(8))
        raiz.add_widget(Cabecalho("Ajustes", self._voltar))

        # rolagem: as opções não cabem numa tela deitada (nem em celular pequeno)
        rolagem = ScrollView(do_scroll_x=False, bar_color=tema.CIANO, bar_width=dp(3))
        lista = GridLayout(cols=1, size_hint_y=None, spacing=dp(4))
        lista.bind(minimum_height=lista.setter("height"))
        rolagem.add_widget(lista)
        raiz.add_widget(rolagem)

        self.alt_voz = Alternar(self._mudar_voz)
        lista.add_widget(Linha("Voz do assistente",
                               "Fala as curvas, as subidas e os avisos da navegacao.",
                               self._centralizar(self.alt_voz)))

        self.sel_qual_voz = Seletor("%s", self._mudar_qual_voz)
        lista.add_widget(Linha("Qual voz",
                               "Vozes do seu celular. Escolha a mais parecida com o Jarvis.",
                               self.sel_qual_voz))

        self.sel_tom = Seletor("%.2f", self._mudar_tom)
        lista.add_widget(Linha("Tom da voz",
                               "Menor: mais grave e calma. Maior: mais aguda.",
                               self.sel_tom))

        self.alt_efeito = Alternar(lambda v: self._mudar_voz_config("voz_efeito", self.alt_efeito, v))
        lista.add_widget(Linha("Efeito de IA",
                               "Tratamento estilo assistente (Jarvis) na voz.",
                               self._centralizar(self.alt_efeito)))

        lista.add_widget(Linha("Testar a voz",
                               "Fala uma frase de exemplo com a voz escolhida.",
                               self._centralizar(BotaoHUD(text="Testar", size_hint_x=None, width=dp(130),
                                                          on_release=lambda *a: self._testar_voz()))))

        self.alt_subidas = Alternar(self._mudar_subidas)
        lista.add_widget(Linha("Avisar subidas",
                               "Na navegacao, avisa antes de cada subida da rota.",
                               self._centralizar(self.alt_subidas)))

        self.alt_girar = Alternar(lambda v: self._mudar_simples("girar_mapa", self.alt_girar, v))
        lista.add_widget(Linha("Mapa gira com a direcao",
                               "Na navegacao, o caminho a frente fica sempre para cima.",
                               self._centralizar(self.alt_girar)))

        self.sel_limite = Seletor("%d km/h", self._mudar_limite)
        lista.add_widget(Linha("Alerta de velocidade",
                               "O velocimetro fica laranja e pisca acima deste valor.",
                               self.sel_limite))

        self.alt_vibrar = Alternar(lambda v: self._mudar_simples("vibrar_limite", self.alt_vibrar, v))
        lista.add_widget(Linha("Vibrar no limite",
                               "O celular vibra quando passa do alerta de velocidade.",
                               self._centralizar(self.alt_vibrar)))

        self.alt_pausa = Alternar(lambda v: self._mudar_simples("pausa_auto", self.alt_pausa, v))
        lista.add_widget(Linha("Pausa automatica",
                               "Parado (semaforo), a viagem pausa sozinha e volta ao andar.",
                               self._centralizar(self.alt_pausa)))

        self.alt_deitada = Alternar(self._mudar_deitada)
        lista.add_widget(Linha("Tela deitada",
                               "Para o celular deitado no suporte do guidao.",
                               self._centralizar(self.alt_deitada)))

        self.alt_tela = Alternar(self._mudar_tela)
        lista.add_widget(Linha("Manter tela ligada",
                               "Evita a tela apagar durante a viagem.",
                               self._centralizar(self.alt_tela)))

        self.sel_alfa = Seletor("%.1f", self._mudar_alfa)
        lista.add_widget(Linha("Resposta do velocimetro",
                               "Menor: numero mais estavel. Maior: reage mais rapido.",
                               self.sel_alfa))

        self.alt_sim = Alternar(self._mudar_sim)
        lista.add_widget(Linha("Modo simulador",
                               "Usa GPS falso para testar o app parado.",
                               self._centralizar(self.alt_sim)))

        self.lbl_versao = Texto(text="", font_size=tema.T_ROTULO, color=tema.CIANO_FRACO,
                                halign="center", size_hint_y=None, height=dp(40))
        lista.add_widget(self.lbl_versao)
        self.add_widget(raiz)

    @staticmethod
    def _centralizar(w):
        caixa = BoxLayout(size_hint_x=None, width=w.width, padding=(0, dp(16)))
        caixa.add_widget(w)
        return caixa

    def on_pre_enter(self, *a):
        aj = App.get_running_app().ajustes
        self.alt_voz.mostrar(aj["voz"])
        self._mostrar_qual_voz()
        self.sel_tom.mostrar(aj["voz_tom"])
        self.alt_efeito.mostrar(aj["voz_efeito"])
        self.alt_subidas.mostrar(aj["avisar_subidas"])
        self.alt_girar.mostrar(aj["girar_mapa"])
        self.sel_limite.mostrar(aj["limite_kmh"])
        self.alt_vibrar.mostrar(aj["vibrar_limite"])
        self.alt_pausa.mostrar(aj["pausa_auto"])
        self.alt_deitada.mostrar(aj["tela_deitada"])
        self.alt_tela.mostrar(aj["tela_ligada"])
        self.sel_alfa.mostrar(aj["alfa"])
        self.alt_sim.mostrar(aj["simulador"])
        self.lbl_versao.text = "GT-HUD versao %s" % _versao()

    def _mudar_limite(self, d):
        aj = App.get_running_app().ajustes
        aj["limite_kmh"] = max(10, min(tema.VEL_MAXIMA, aj["limite_kmh"] + d))
        self.sel_limite.mostrar(aj["limite_kmh"])

    def _mudar_simples(self, chave, botao, ligado):
        App.get_running_app().ajustes[chave] = ligado
        botao.mostrar(ligado)

    def _mudar_voz(self, ligado):
        app = App.get_running_app()
        app.ajustes["voz"] = ligado
        app.voz.ligada = ligado
        if not ligado:
            app.voz.calar()
        self.alt_voz.mostrar(ligado)

    def _mostrar_qual_voz(self):
        app = App.get_running_app()
        n = len(app.voz.nomes_vozes())
        i = app.ajustes["voz_indice"]
        if n == 0:
            self.sel_qual_voz.mostrar("gravada")
        else:
            self.sel_qual_voz.mostrar("padrao" if i < 0 or i >= n else "%d de %d" % (i + 1, n))

    def _mudar_qual_voz(self, d):
        app = App.get_running_app()
        n = len(app.voz.nomes_vozes())
        if n == 0:
            return  # sem motor de voz em português: fica a voz gravada
        atual = app.ajustes["voz_indice"]   # -1 = padrão do celular (só no começo)
        app.ajustes["voz_indice"] = (0 if d > 0 else n - 1) if atual < 0 else (atual + d) % n
        self._aplicar_voz(testar=True)
        self._mostrar_qual_voz()

    def _mudar_tom(self, d):
        app = App.get_running_app()
        app.ajustes["voz_tom"] = round(max(0.70, min(1.20, app.ajustes["voz_tom"] + d * 0.04)), 2)
        self.sel_tom.mostrar(app.ajustes["voz_tom"])
        self._aplicar_voz(testar=True)

    def _mudar_voz_config(self, chave, botao, ligado):
        App.get_running_app().ajustes[chave] = ligado
        botao.mostrar(ligado)
        self._aplicar_voz(testar=True)

    def _aplicar_voz(self, testar=False):
        app = App.get_running_app()
        aj = app.ajustes
        app.voz.configurar(aj["voz_indice"], aj["voz_tom"], aj["voz_efeito"])
        if testar:
            self._testar_voz()

    def _testar_voz(self):
        app = App.get_running_app()
        app.voz.calar()
        app.voz.testar()

    def _mudar_subidas(self, ligado):
        app = App.get_running_app()
        app.ajustes["avisar_subidas"] = ligado
        if app.nav is not None:
            app.nav.avisar_subidas = ligado
        self.alt_subidas.mostrar(ligado)

    def _mudar_deitada(self, ligado):
        app = App.get_running_app()
        app.ajustes["tela_deitada"] = ligado
        app.aplicar_orientacao()
        self.alt_deitada.mostrar(ligado)

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
        App.get_running_app().voltar()
