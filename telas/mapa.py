"""Tela principal: mapa + velocímetro, no estilo Waze com o visual do GT-HUD.

Três modos:
  livre      mapa seguindo quem pedala, velocímetro, gravação de viagem e a
             busca "Para onde, senhor?"
  previa     rota calculada até o destino: resumo, altimetria e "Iniciar"
  navegando  faixa da próxima manobra, aviso de subida, tempo/km/subida que
             faltam e o mapa girando com a direção

Tudo por cima do mapa é posicionado à mão em _posicionar() (em pé e deitada):
widget escondido sai do layout, para não roubar o toque do mapa.
"""
from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

import android_utils
import busca
import goiania
import tema
from falas import texto_manobra
from util import fmt_dist, fmt_dist_nav, fmt_duracao, fmt_hora_chegada, fmt_tempo
from viagem import Viagem
from widgets.botao import BotaoHUD
from widgets.comuns import Aviso, PainelHUD, Ponto, Texto, escolher, pedir_nome
from widgets.manobra import IconeManobra
from widgets.mapa import MapaHUD
from widgets.perfil import PerfilAltimetria
from widgets.velocimetro import Velocimetro

RESUMO_FICA_S = 20.0   # o cartão de resumo da rota some sozinho depois disso
LIVRE, PREVIA, NAVEGANDO = "livre", "previa", "navegando"
TRILHA_A_CADA_S = 3


class DiscoVelocimetro(Widget):
    """Velocímetro compacto num disco escuro por cima do mapa."""

    def __init__(self, **kw):
        kw.setdefault("size_hint", (None, None))
        super().__init__(**kw)
        self.velo = Velocimetro(compacto=True)
        self.add_widget(self.velo)
        self.bind(pos=self._d, size=self._d)

    def _d(self, *a):
        self.velo.pos = (self.x + dp(2), self.y + dp(2))
        self.velo.size = (self.width - dp(4), self.height - dp(4))
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*tema.com_alfa(tema.CIANO, 0.10))   # halo em volta do disco
            Line(ellipse=(self.x, self.y, self.width, self.height), width=dp(4))
            Color(*tema.com_alfa(tema.FUNDO, 0.92))
            Ellipse(pos=self.pos, size=self.size)
            Color(*tema.com_alfa(tema.CIANO, 0.55))
            Line(ellipse=(self.x, self.y, self.width, self.height), width=dp(1.2))


class ChipStatus(BoxLayout):
    """Bolinha + texto do GPS num fundo escuro do tamanho do texto (direto
    sobre o mapa, o texto se misturava com ruas e nomes). Não passa de
    `largura_max` (os botões do menu ficam ao lado): se o texto não cabe,
    quebra a linha e o chip cresce para baixo, com o topo em `topo_alvo`."""
    largura_max = NumericProperty(dp(400))
    topo_alvo = NumericProperty(0)

    def __init__(self, **kw):
        kw.setdefault("size_hint", (None, None))
        kw.setdefault("spacing", dp(6))
        kw.setdefault("padding", (dp(8), dp(4)))
        super().__init__(**kw)
        self.ponto = Ponto(pos_hint={"center_y": 0.5})
        self.lbl = Label(text="Buscando GPS", font_size=tema.T_ROTULO + 1, color=tema.BRANCO,
                         size_hint_x=None, halign="left", valign="middle")
        self.add_widget(self.ponto)
        self.add_widget(self.lbl)
        with self.canvas.before:
            Color(*tema.com_alfa(tema.FUNDO, 0.8))
            self._fundo = RoundedRectangle(radius=[dp(10)])
        self.lbl.bind(texture_size=self._ajustar, text=self._medir_de_novo)
        self.bind(pos=self._d, size=self._d, largura_max=self._medir_de_novo,
                  topo_alvo=self._ajustar)
        self._ajustar()

    def _medir_de_novo(self, *a):
        self.lbl.text_size = (None, None)  # tamanho natural; _ajustar decide se quebra
        self._ajustar()

    def _ajustar(self, *a):
        fixo = self.padding[0] + self.padding[2] + self.ponto.width + self.spacing
        livre = max(dp(40), self.largura_max - fixo)
        w, h = self.lbl.texture_size
        if self.lbl.text_size[0] is None and w > livre:
            self.lbl.text_size = (livre, None)  # quebra a linha (volta aqui com a textura nova)
            return
        self.lbl.width = min(w, livre)
        self.width = fixo + self.lbl.width
        self.height = max(dp(40), h + self.padding[1] + self.padding[3])
        self.y = self.topo_alvo - self.height

    def _d(self, *a):
        self._fundo.pos, self._fundo.size = self.pos, self.size


class EscolhaRotas(BoxLayout):
    """Uma "aba" por rota (nome curto, tempo e km); a escolhida fica acesa."""

    def __init__(self, **kw):
        kw.setdefault("spacing", dp(6))
        super().__init__(**kw)

    @staticmethod
    def nome_curto(rota):
        n = rota.nome_perfil.replace("Mais ", "").replace("Menos subida", "plana")
        return n[:1].upper() + n[1:]

    def mostrar(self, rotas, escolhida, ao_escolher):
        self.clear_widgets()
        for i, r in enumerate(rotas):
            b = BotaoHUD(text="%s\n%s  %s" % (self.nome_curto(r), fmt_duracao(r.tempo_s),
                                              fmt_dist_nav(r.total_m)),
                         destaque=(r is escolhida), font_size=tema.T_ROTULO,
                         halign="center", valign="middle", max_lines=2,
                         on_release=lambda w, rr=r: ao_escolher(rr))
            # texto centralizado em cada linha (sem text_size, a 2ª linha
            # ficava torta em relação à 1ª)
            b.bind(size=lambda w, t: setattr(w, "text_size", (t[0] - dp(8), t[1])))
            self.add_widget(b)


class Coluna(BoxLayout):
    """Número grande com rótulo pequeno embaixo (barras de baixo)."""

    def __init__(self, rotulo, **kw):
        kw.setdefault("orientation", "vertical")
        super().__init__(**kw)
        # uma linha cada (com a fonte grande do celular, "chegada 13:14"
        # quebrava em duas e encavalava)
        self.valor = Texto(text="-", font_size=sp(22), bold=True, halign="center",
                           shorten=True, max_lines=1)
        self.rotulo = Texto(text=rotulo, font_size=tema.T_ROTULO, color=tema.CIANO_FRACO,
                            halign="center", size_hint_y=0.6, shorten=True, max_lines=1)
        self.add_widget(self.valor)
        self.add_widget(self.rotulo)


class TelaMapa(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        app = App.get_running_app()
        self.estado = LIVRE
        self._deitada = None
        self._ev_tique = None
        self._ev_msg = None
        self._t_trilha = 0
        self._confirmando_fim = False
        self._tem_depois = False
        self._tem_subida = False
        self._tem_alerta = False

        self.raiz = FloatLayout()
        self.mapa = MapaHUD(app.user_data_dir, girar=app.ajustes["girar_mapa"])
        self.raiz.add_widget(self.mapa)
        self.mapa.bind(seguindo=lambda *a: self._montar())

        # --- livre: busca, status do GPS e menu ---
        self.busca = BotaoHUD(text="Para onde, senhor?", destaque=True, size_hint=(None, None),
                              on_release=lambda *a: app.abrir("busca"))
        self.status = ChipStatus()
        self.ponto, self.lbl_gps = self.status.ponto, self.status.lbl
        self.menu = BoxLayout(size_hint=(None, None), spacing=dp(6))
        for texto, tela in (("Painel", "hud"), ("Viagens", "viagens"), ("Ajustes", "config")):
            self.menu.add_widget(BotaoHUD(text=texto, font_size=tema.T_ROTULO + 1, opaco=True,
                                          on_release=lambda *a, t=tela: app.abrir(t)))

        # --- navegando: faixa da manobra, "depois", subida ---
        self.faixa = PainelHUD(size_hint=(None, None))
        self.icone = IconeManobra(size_hint_x=None, width=dp(84))
        textos = BoxLayout(orientation="vertical", spacing=dp(2))
        self.lbl_dist = Texto(text="", font_size=sp(38), bold=True, size_hint_y=1.35)
        self.lbl_instr = Texto(text="", font_size=sp(18), color=tema.BRANCO)
        self.lbl_rua = Texto(text="", font_size=sp(19), bold=True, color=tema.CIANO)
        for w in (self.lbl_dist, self.lbl_instr, self.lbl_rua):
            textos.add_widget(w)
        self.faixa.add_widget(self.icone)
        self.faixa.add_widget(textos)
        self.depois = PainelHUD(size_hint=(None, None), padding=(dp(10), dp(4)))
        self.depois.add_widget(Texto(text="Depois", font_size=tema.T_ROTULO, color=tema.CIANO_FRACO))
        self.icone_depois = IconeManobra(size_hint_x=None, width=dp(30))
        self.depois.add_widget(self.icone_depois)
        self.chip_subida = PainelHUD(size_hint=(None, None), cor_borda=tema.LARANJA,
                                     padding=(dp(12), dp(4)))
        self.lbl_subida = Texto(text="", font_size=tema.T_BOTAO, bold=True, color=tema.LARANJA)
        self.chip_subida.add_widget(self.lbl_subida)
        self.chip_alerta = PainelHUD(size_hint=(None, None), cor_borda=tema.VERMELHO,
                                     padding=(dp(12), dp(4)))
        self.lbl_alerta = Texto(text="", font_size=tema.T_BOTAO, bold=True, color=tema.BRANCO)
        self.chip_alerta.add_widget(self.lbl_alerta)

        # --- velocímetro e botões do mapa ---
        self.disco = DiscoVelocimetro()
        # botões do mapa com ÍCONE (lê mais rápido que palavra, com a bike andando)
        self.btn_centro = BotaoHUD(text="", icone="centralizar", opaco=True, destaque=True,
                                   size_hint=(None, None), on_release=lambda *a: self.mapa.recentralizar())
        self.btn_mais = BotaoHUD(text="", icone="mais", size_hint=(None, None), opaco=True,
                                 on_release=lambda *a: self.mapa.mudar_zoom(1))
        self.btn_menos = BotaoHUD(text="", icone="menos", size_hint=(None, None), opaco=True,
                                  on_release=lambda *a: self.mapa.mudar_zoom(-1))
        self.lbl_msg = Aviso(text="", font_size=tema.T_ROTULO + 1, bold=True, size_hint=(None, None))

        # --- barra de baixo: livre (viagem) ---
        self.barra_livre = PainelHUD(size_hint=(None, None))
        self.col_dist = Coluna("Distância")
        self.col_tempo = Coluna("Tempo")
        self.controles = BoxLayout(spacing=dp(8), size_hint_x=1.6)
        for w in (self.col_dist, self.col_tempo, self.controles):
            self.barra_livre.add_widget(w)

        # --- barra de baixo: navegando ---
        self.barra_nav = PainelHUD(size_hint=(None, None))
        self.col_tempo_nav = Coluna("chegada")
        self.col_falta = Coluna("faltam")
        self.col_sobe = Coluna("de subida")
        # botões grandes: dá para acertar com a bike tremendo
        self.btn_encerrar = BotaoHUD(text="Encerrar", cor=tema.VERMELHO, font_size=tema.T_ROTULO + 2,
                                     size_hint_x=0.95, on_release=lambda *a: self._encerrar())
        self.btn_rotas = BotaoHUD(text="Rotas", icone="rotas", size_hint=(None, None), opaco=True,
                                  font_size=sp(11), on_release=lambda *a: app.calcular_rotas_navegando())
        self.btn_vivo = BotaoHUD(text="Ao vivo", icone="vivo", size_hint=(None, None), opaco=True,
                                 font_size=sp(11), on_release=lambda *a: self._ao_vivo())
        for w in (self.col_tempo_nav, self.col_falta, self.col_sobe, self.btn_encerrar):
            self.barra_nav.add_widget(w)

        # --- navegando: escolher outra rota até o destino ---
        self._escolha_nav = None   # None, "calculando" ou (rotas, escolhida)
        self.painel_rotas = PainelHUD(orientation="vertical", size_hint=(None, None), spacing=dp(6))
        self.lbl_rotas = Texto(text="", font_size=tema.T_ROTULO + 2, bold=True, color=tema.CIANO,
                               size_hint_y=None, height=dp(22))
        self.escolha_nav = EscolhaRotas(size_hint_y=None, height=dp(50))
        botoes_esc = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        botoes_esc.add_widget(BotaoHUD(text="Manter a atual", font_size=tema.T_ROTULO + 2,
                                       on_release=lambda *a: self.fechar_escolha_nav()))
        self.btn_usar = BotaoHUD(text="Usar esta", destaque=True, font_size=tema.T_ROTULO + 2,
                                 on_release=lambda *a: self._usar_escolhida())
        botoes_esc.add_widget(self.btn_usar)
        for w in (self.lbl_rotas, self.escolha_nav, botoes_esc):
            self.painel_rotas.add_widget(w)

        # --- prévia da rota ---
        self.card = PainelHUD(orientation="vertical", size_hint=(None, None), spacing=dp(6))
        self.lbl_destino = Texto(text="", font_size=tema.T_BOTAO + 1, bold=True, color=tema.CIANO,
                                 shorten=True, shorten_from="right", max_lines=1,
                                 size_hint_y=None, height=dp(26))
        self.lbl_resumo = Texto(text="", font_size=tema.T_ROTULO + 2, size_hint_y=None, height=dp(22),
                                shorten=True, shorten_from="right", max_lines=1)
        self.perfil = PerfilAltimetria(size_hint_y=None, height=dp(64))
        self.escolha = EscolhaRotas(size_hint_y=None, height=dp(50))
        botoes = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        botoes.add_widget(BotaoHUD(text="Cancelar", on_release=lambda *a: app.cancelar_previa()))
        self.btn_iniciar = BotaoHUD(text="Iniciar", destaque=True,
                                    on_release=lambda *a: app.iniciar_navegacao())
        botoes.add_widget(self.btn_iniciar)
        for w in (self.lbl_destino, self.lbl_resumo, self.escolha, self.perfil, botoes):
            self.card.add_widget(w)

        # --- resumo da rota que acabou (chegou ou encerrou) ---
        self._resumo = False
        self._ev_resumo = None
        self._manobra_vista = None
        self.card_resumo = PainelHUD(orientation="vertical", size_hint=(None, None), spacing=dp(6))
        self.lbl_resumo_titulo = Texto(text="", font_size=tema.T_TITULO, bold=True, color=tema.VERDE,
                                       halign="center", size_hint_y=None, height=dp(32))
        self.lbl_resumo_destino = Texto(text="", font_size=tema.T_ROTULO + 2, color=tema.CIANO_FRACO,
                                        halign="center", shorten=True, shorten_from="right", max_lines=1,
                                        size_hint_y=None, height=dp(22))
        numeros = BoxLayout(spacing=dp(6))
        self.res_dist, self.res_tempo = Coluna("distância"), Coluna("tempo")
        self.res_media, self.res_max = Coluna("média km/h"), Coluna("máxima km/h")
        for w in (self.res_dist, self.res_tempo, self.res_media, self.res_max):
            numeros.add_widget(w)
        self.card_resumo.add_widget(self.lbl_resumo_titulo)
        self.card_resumo.add_widget(self.lbl_resumo_destino)
        self.card_resumo.add_widget(numeros)
        self.card_resumo.add_widget(BotaoHUD(text="Fechar", size_hint_y=None, height=dp(48),
                                             font_size=tema.T_ROTULO + 2,
                                             on_release=lambda *a: self._fechar_resumo()))

        # --- ponto marcado (segurar o dedo no mapa) ---
        self._marca = None
        self.card_marca = PainelHUD(orientation="vertical", size_hint=(None, None), spacing=dp(8))
        self.lbl_marca = Texto(text="Ponto marcado", font_size=tema.T_BOTAO, bold=True,
                               color=tema.CIANO, size_hint_y=None, height=dp(26))
        botoes_marca = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        botoes_marca.add_widget(BotaoHUD(text="Fechar", font_size=tema.T_ROTULO + 2,
                                         on_release=lambda *a: self._fechar_marca()))
        botoes_marca.add_widget(BotaoHUD(text="Salvar", font_size=tema.T_ROTULO + 2,
                                         on_release=lambda *a: self._pedir_nome()))
        botoes_marca.add_widget(BotaoHUD(text="Ir para cá", destaque=True, font_size=tema.T_ROTULO + 2,
                                         on_release=lambda *a: self._ir_marca()))
        self.card_marca.add_widget(self.lbl_marca)
        self.card_marca.add_widget(botoes_marca)
        self.mapa.ao_segurar = self._ao_segurar

        self.add_widget(self.raiz)
        self.bind(size=self._posicionar)
        self._montar()

    # --- ciclo de vida ---------------------------------------------------------
    def on_pre_enter(self, *a):
        app = App.get_running_app()
        if not getattr(self, "_ouvindo", False):
            app.ouvir(self._ao_ler)
            self._ouvindo = True
        self.mapa.girar = app.ajustes["girar_mapa"]
        self.disco.velo.limite = app.ajustes["limite_kmh"]
        self._montar_controles()
        self._atualizar_viagem()
        if self._ev_tique is None:
            self._ev_tique = Clock.schedule_interval(self._tique, 1.0)
        self.mapa.retomar()

    def on_leave(self, *a):
        if self._ev_tique is not None:
            self._ev_tique.cancel()
            self._ev_tique = None
        self.mapa.pausar()  # fora de vista o mapa não anima (bateria e fluidez)

    # --- modos (chamados pelo app) -----------------------------------------------
    def modo_livre(self, mensagem=None, cor=None):
        self.estado = LIVRE
        self._marca = None
        self._tem_depois = self._tem_subida = self._tem_alerta = False
        self.mapa.modo_navegacao(False)
        self.mapa.sinais_rota = None
        self.mapa.definir_rota([])
        self.mapa.definir_destino(None)
        self.mapa.recentralizar()
        self._montar()
        if mensagem:
            self.mensagem(mensagem, cor or tema.VERDE)

    def mostrar_resumo(self, titulo, destino, resumo):
        """Cartão de fechamento da rota: distância, tempo, média e máxima.
        Fica até tocar em Fechar (ou some sozinho em RESUMO_FICA_S)."""
        self.lbl_resumo_titulo.text = titulo
        self.lbl_resumo_destino.text = destino or ""
        self.res_dist.valor.text = fmt_dist(resumo["distancia_m"])
        self.res_tempo.valor.text = fmt_tempo(resumo["duracao_s"])
        self.res_media.valor.text = "%.0f" % (resumo["vel_media_kmh"] or 0)
        self.res_max.valor.text = "%.0f" % (resumo["vel_max_kmh"] or 0)
        self._resumo = True
        if self._ev_resumo is not None:
            self._ev_resumo.cancel()
        self._ev_resumo = Clock.schedule_once(lambda dt: self._fechar_resumo(), RESUMO_FICA_S)
        self._montar()
        self.card_resumo.opacity = 0.0
        Animation(opacity=1.0, d=0.3, t="out_quad").start(self.card_resumo)

    def _fechar_resumo(self, montar=True):
        if self._ev_resumo is not None:
            self._ev_resumo.cancel()
            self._ev_resumo = None
        if self._resumo:
            self._resumo = False
            if montar:
                self._montar()

    def previa_calculando(self, lugar):
        self._fechar_resumo(montar=False)
        self.estado = PREVIA
        self.lbl_destino.text = lugar["nome"]
        self.lbl_resumo.text = "Calculando a rota..."
        self.lbl_resumo.color = tema.CIANO_FRACO
        self.escolha.clear_widgets()
        self.mapa.definir_alternativas([])
        self.perfil.elevacao = []
        self.btn_iniciar.disabled = True
        self.mapa.definir_destino((lugar["lat"], lugar["lon"]))
        self._montar()

    def mostrar_previa(self, rota, rotas=None, enquadrar=True):
        """Rota escolhida (+ as outras opções, em abas e em cinza no mapa)."""
        self.estado = PREVIA
        rotas = rotas or [rota]
        app = App.get_running_app()
        self.escolha.mostrar(rotas, rota, app.escolher_rota_previa)
        if len(rotas) == 1 and app.calculando_alternativas:
            self.escolha.add_widget(Texto(text="Buscando outras\nrotas...", font_size=tema.T_ROTULO,
                                          color=tema.CIANO_FRACO, halign="center"))
        self.mapa.definir_alternativas([r.pontos for r in rotas if r is not rota])
        n = len(rota.subidas)
        self.lbl_resumo.text = "%s  |  %s  |  sobe %d m  |  %d %s" % (
            fmt_dist_nav(rota.total_m), fmt_duracao(rota.tempo_s), rota.subida_total_m,
            n, "subida" if n == 1 else "subidas") if n else "%s  |  %s  |  sobe %d m" % (
            fmt_dist_nav(rota.total_m), fmt_duracao(rota.tempo_s), rota.subida_total_m)
        self.lbl_resumo.color = tema.BRANCO
        self.perfil.subidas = rota.subidas
        self.perfil.elevacao = rota.elevacao
        self.btn_iniciar.disabled = False
        self.mapa.definir_rota(rota.pontos)
        self.mapa.definir_destino(rota.pontos[-1])
        self._montar()
        if enquadrar:
            todos = [p for r in rotas for p in r.pontos]
            Clock.schedule_once(lambda dt: self.mapa.enquadrar(todos, dp(36), self._cobertos_previa()))

    def previa_erro(self, texto):
        self.lbl_resumo.text = texto
        self.lbl_resumo.color = tema.VERMELHO
        self.btn_iniciar.disabled = True

    def modo_navegando(self, rota):
        self.estado = NAVEGANDO
        self._manobra_vista = None
        self._fechar_resumo(montar=False)
        self._tem_depois = self._tem_subida = self._tem_alerta = False
        self._confirmando_fim = False
        self.btn_encerrar.text = "Encerrar"
        self._escolha_nav = None
        self.mapa.definir_alternativas([])
        self.mapa.definir_rota(rota.pontos)
        self.mapa.definir_destino(rota.pontos[-1])
        self.mapa.modo_navegacao(True)
        self.mapa.prever = App.get_running_app().nav.prever  # seta anda em cima da rota
        self._sinais_da_rota()
        self._montar()

    def trocar_rota(self, rota):
        self.mapa.definir_rota(rota.pontos)
        self._sinais_da_rota()

    def _sinais_da_rota(self):
        """Navegando, o mapa mostra só os semáforos/lombadas do caminho."""
        nav = App.get_running_app().nav
        if nav is None:
            self.mapa.sinais_rota = None
            return
        self.mapa.sinais_rota = [nav.rota.ponto_em(d)[:2] + (tipo,) for d, tipo in nav.alertas]

    # --- navegando: escolher outra rota -----------------------------------------------
    def escolha_nav_calculando(self):
        self._escolha_nav = "calculando"
        self.lbl_rotas.text = "Calculando rotas daqui até o destino..."
        self.escolha_nav.clear_widgets()
        self.btn_usar.disabled = True
        self._montar()

    def mostrar_escolha_nav(self, rotas, escolhida=None):
        if self._escolha_nav is None:
            return  # fechou enquanto calculava
        escolhida = escolhida or rotas[0]
        self._escolha_nav = (rotas, escolhida)
        n = len(rotas)
        self.lbl_rotas.text = ("%d rotas daqui até o destino" % n) if n > 1 else \
            "Só há um bom caminho daqui até o destino"
        self.escolha_nav.mostrar(rotas, escolhida, lambda r: self.mostrar_escolha_nav(rotas, r))
        self.btn_usar.disabled = False
        self.mapa.definir_rota(escolhida.pontos)
        self.mapa.definir_alternativas([r.pontos for r in rotas if r is not escolhida])
        self._montar()

    def fechar_escolha_nav(self):
        self._escolha_nav = None
        app = App.get_running_app()
        self.mapa.definir_alternativas([])
        if app.nav is not None:
            self.mapa.definir_rota(app.nav.rota.pontos)
        self._montar()

    def _usar_escolhida(self):
        if isinstance(self._escolha_nav, tuple):
            rota = self._escolha_nav[1]
            self._escolha_nav = None
            self.mapa.definir_alternativas([])
            App.get_running_app().trocar_rota_navegando(rota)
            self._montar()

    def mensagem(self, texto, cor=tema.VERDE, segundos=3.5):
        self.lbl_msg.text = texto
        self.lbl_msg.color = cor
        if self._ev_msg:
            self._ev_msg.cancel()
        self._ev_msg = Clock.schedule_once(lambda dt: setattr(self.lbl_msg, "text", ""), segundos)

    # --- montagem e posição dos elementos -----------------------------------------
    def _montar(self, *a):
        visiveis = [self.mapa, self.disco, self.lbl_msg, self.btn_mais, self.btn_menos]
        if not self.mapa.seguindo:
            visiveis.append(self.btn_centro)
        if self.estado == LIVRE and self._marca is not None:
            visiveis += [self.busca, self.status, self.menu, self.card_marca]
            visiveis.remove(self.disco)
        elif self.estado == LIVRE:
            visiveis += [self.busca, self.status, self.menu, self.barra_livre]
            if self._resumo:
                visiveis.append(self.card_resumo)
        elif self.estado == PREVIA:
            visiveis += [self.status, self.card]
            visiveis.remove(self.disco)
        else:
            visiveis += [self.faixa, self.barra_nav]
            if self._escolha_nav is None:
                visiveis += [self.btn_rotas, self.btn_vivo]
                self._pintar_vivo()
            if self._escolha_nav is not None:
                visiveis.append(self.painel_rotas)
                visiveis.remove(self.disco)
            if self._tem_depois:
                visiveis.append(self.depois)
            if self._tem_subida:
                visiveis.append(self.chip_subida)
            if self._tem_alerta:
                visiveis.append(self.chip_alerta)
        for w in list(self.raiz.children):
            if w not in visiveis:
                self.raiz.remove_widget(w)
        for w in visiveis:  # na ordem: o mapa fica embaixo de tudo
            if w.parent is None:
                self.raiz.add_widget(w)
        self._posicionar()

    def _cobertos_previa(self):
        """Área tapada pelo cartão da prévia (embaixo em pé, à direita deitada)
        e pela linha do GPS em cima."""
        m = dp(10)
        if self.width > self.height:
            return (0, 0, self.card.width + 2 * m, dp(44))
        return (0, self.card.height + 2 * m, 0, dp(44))

    def _posicionar(self, *a):
        W, H = self.width, self.height
        if W < 10:
            return
        m = dp(10)
        deitada = W > H
        topo = H - m
        tam_velo = dp(124) if deitada else dp(150)
        alt_barra = dp(76)

        # barra de baixo e velocímetro
        if deitada:
            bx, bw = m + tam_velo + m, W - tam_velo - 3 * m
            self.disco.pos = (m, m)
        else:
            bx, bw = m, W - 2 * m
            self.disco.pos = (m, m + alt_barra + m)
        self.disco.size = (tam_velo, tam_velo)
        for barra in (self.barra_livre, self.barra_nav):
            barra.pos, barra.size = (bx, m), (bw, alt_barra)

        # topo
        larg_topo = min(W - 2 * m, dp(480))
        col = larg_topo
        if deitada:  # coluna da esquerda (curva, avisos); o mapa fica com a direita
            col = min(W * 0.42, dp(400))
        self.busca.pos, self.busca.size = (m, topo - dp(54)), (larg_topo, dp(54))
        larg_menu = 3 * dp(74) + 2 * dp(6)
        self.menu.pos, self.menu.size = (W - m - larg_menu, topo - dp(54) - m - dp(40)), (larg_menu, dp(40))
        self.status.x = m
        self.status.topo_alvo = topo - dp(54) - m
        self.status.largura_max = W - 3 * m - larg_menu
        self.faixa.pos, self.faixa.size = (m, topo - dp(132)), (col, dp(132))
        self.depois.pos, self.depois.size = (m, topo - dp(132) - dp(6) - dp(38)), (dp(118), dp(38))
        larg_chip = min(col, dp(330))
        y_chip = topo - dp(132) - dp(6) - dp(44)
        if self._tem_depois:
            y_chip -= dp(44)
        self.chip_subida.pos, self.chip_subida.size = (m, y_chip), (larg_chip, dp(44))
        y_alerta = y_chip - (dp(50) if self._tem_subida else 0)
        self.chip_alerta.pos, self.chip_alerta.size = (m, y_alerta), (min(larg_chip, dp(250)), dp(44))
        if self.estado == PREVIA:
            self.status.topo_alvo = topo
            self.status.largura_max = W - 2 * m

        # prévia
        larg_card = min(W - 2 * m, dp(480))
        self.card.size = (larg_card, dp(268))
        self.painel_rotas.pos = (m, m + alt_barra + m) if not deitada else (bx, m + alt_barra + m)
        self.painel_rotas.size = (larg_topo if not deitada else min(bw, dp(480)), dp(150))
        self.card.pos = (W - m - larg_card, m) if deitada else (m, m)

        # botões do mapa (direita, acima da barra)
        base = m + alt_barra + m if self.estado != PREVIA else m + self.card.height + m
        if self.estado == NAVEGANDO and self._escolha_nav is not None:
            base += dp(150) + m
        self.card_marca.pos = (m, m)
        self.card_marca.size = (min(W - 2 * m, dp(480)), dp(110))
        larg_res = min(W - 2 * m, dp(440))
        self.card_resumo.size = (larg_res, dp(214))
        self.card_resumo.pos = ((W - larg_res) / 2.0, max(m + alt_barra + m, (H - dp(214)) / 2.0))
        if self.estado == LIVRE and self._marca is not None:
            base = m + dp(110) + m
        if deitada and self.estado == PREVIA:
            base = m
        lb, ab, gap = dp(58), dp(54), dp(8)   # botões do mapa: grandes para o guidão
        x_btn = W - m - lb if not (deitada and self.estado == PREVIA) else W - larg_card - 2 * m - lb
        self.btn_menos.pos, self.btn_menos.size = (x_btn, base), (lb, ab)
        self.btn_mais.pos, self.btn_mais.size = (x_btn, base + ab + gap), (lb, ab)
        y_extra = base + 2 * (ab + gap)
        if self.estado == NAVEGANDO and self._escolha_nav is None:
            alto = ab + dp(8)   # ícone + nome embaixo
            self.btn_rotas.pos, self.btn_rotas.size = (x_btn, y_extra), (lb, alto)
            y_extra += alto + gap
            self.btn_vivo.pos, self.btn_vivo.size = (x_btn, y_extra), (lb, alto)
            y_extra += alto + gap
        self.btn_centro.pos = (x_btn, y_extra)
        self.btn_centro.size = (lb, ab)

        # mensagem curta
        if deitada:
            self.lbl_msg.pos, self.lbl_msg.size = (bx, m + alt_barra + dp(4)), (bw, dp(36))
        else:
            self.lbl_msg.pos = (m + tam_velo + m, m + alt_barra + m)
            self.lbl_msg.size = (W - tam_velo - 3 * m - dp(60), dp(44))
        # seta navegando: no meio da parte livre do mapa (deitada: à direita da coluna)
        if deitada:
            self.mapa.ancora_nav = ((m + col + W) / 2.0 / W, 0.40)
        else:
            self.mapa.ancora_nav = (0.5, 0.30)
        if self.estado == NAVEGANDO and self.mapa.girar and self.mapa.ancora != self.mapa.ancora_nav:
            self.mapa.ancora = self.mapa.ancora_nav
        # crédito do OpenStreetMap: à esquerda da coluna de botões (não por baixo dela)
        self.mapa.credito_margem = (W - x_btn + m, base + dp(2) if self.estado != PREVIA else m)
        # nomes do mapa não vão para baixo dos painéis (ficavam escondidos)
        self.mapa.areas_cobertas = [(w.x, w.y, w.right, w.top) for w in self.raiz.children
                                    if w is not self.mapa and w is not self.lbl_msg]
        self.mapa._aplicar()

    # --- ponto marcado: segurar o dedo no mapa --------------------------------------
    def _ao_segurar(self, lat, lon):
        if self.estado != LIVRE:
            return  # na prévia/navegação o dedo no mapa é só para olhar
        if not goiania.dentro(lat, lon):
            self.mensagem("Fora de Goiânia", tema.LARANJA)
            return
        android_utils.vibrar([0, 35], [0, 160])  # "pegou": dá para sentir sem olhar
        self._marca = (lat, lon)
        self.lbl_marca.text = "Ponto marcado: salvar ou ir para cá?"
        self.mapa.definir_destino(self._marca)
        self._montar()

    def _fechar_marca(self):
        self._marca = None
        self.mapa.definir_destino(None)
        self._montar()

    def _ir_marca(self):
        if self._marca is None:
            return
        lat, lon = self._marca
        self._marca = None
        App.get_running_app().escolher_destino({"nome": "Ponto marcado", "endereco": "",
                                                "lat": lat, "lon": lon})

    def _pedir_nome(self):
        if self._marca is None:
            return
        lat, lon = self._marca

        def salvar(nome):
            App.get_running_app().salvar_lugar(nome, lat, lon)
            self._fechar_marca()
            self.mensagem("Salvo! Ache em \"Para onde, senhor?\"", tema.VERDE)
        # já sugere o lugar conhecido naquele ponto, se houver
        pedir_nome(salvar, sugestao=busca.nome_perto(lat, lon))

    # --- corrida ao vivo ---------------------------------------------------------------
    def _pintar_vivo(self):
        ligado = App.get_running_app().compartilhando()
        self.btn_vivo.text = "No ar" if ligado else "Ao vivo"
        self.btn_vivo.cor = tema.VERDE if ligado else tema.CIANO

    def _ao_vivo(self):
        app = App.get_running_app()
        if app.compartilhando():
            escolher("Corrida ao vivo", [
                ("Enviar o link de novo", self._compartilhar),
                ("Parar de compartilhar", self._parar_vivo),
                ("Fechar", None)])
        else:
            self._compartilhar()

    def _compartilhar(self):
        app = App.get_running_app()
        resposta = app.compartilhar_corrida()
        if resposta == "sem_config":
            escolher("Corrida ao vivo", [("Abrir os Ajustes", lambda: app.abrir("config")), ("Agora não", None)],
                     texto="Falta um passo, feito uma vez só: colar nos Ajustes o endereço do seu "
                           "banco gratuito (linha \"Corrida ao vivo\").")
        elif resposta != "sem_rota":
            self.mensagem("Link pronto: escolha o contato", tema.VERDE)
        self._pintar_vivo()

    def _parar_vivo(self):
        App.get_running_app().parar_corrida()
        self.mensagem("Parou de compartilhar: o link não mostra mais nada", tema.LARANJA, 5)
        self._pintar_vivo()

    # --- viagem (modo livre) --------------------------------------------------------
    def _montar_controles(self):
        v = App.get_running_app().viagem
        c = self.controles
        c.clear_widgets()
        if v.estado == Viagem.PARADA:
            # sem botão de gravar (pedido do dono, 06/10/2026): a viagem grava
            # sozinha em toda rota iniciada, e só nelas
            aviso = Texto(text="Toda rota iniciada\né gravada sozinha", font_size=tema.T_ROTULO,
                          color=tema.CIANO_FRACO, halign="center")
            c.add_widget(aviso)
        self._estado_viagem = v.estado

    def _atualizar_viagem(self):
        app = App.get_running_app()
        v = app.viagem
        if v.estado == Viagem.PARADA:   # andando livre: o total das rotas de hoje
            metros, segundos = app.resumo_de_hoje()
            self.col_dist.valor.text, self.col_dist.rotulo.text = fmt_dist(metros), "hoje"
            self.col_tempo.valor.text, self.col_tempo.rotulo.text = fmt_tempo(segundos), "andando hoje"
        else:
            self.col_dist.valor.text, self.col_dist.rotulo.text = fmt_dist(v.distancia_m), "Distância"
            self.col_tempo.valor.text, self.col_tempo.rotulo.text = fmt_tempo(v.tempo_total_s), "Tempo"
        if v.estado != getattr(self, "_estado_viagem", None):
            self._montar_controles()  # a pausa automática mudou o estado

    def _encerrar(self):
        if not self._confirmando_fim:
            self._confirmando_fim = True
            self.btn_encerrar.text = "Toque de novo"
            Clock.schedule_once(lambda dt: self._cancelar_fim(), 3)
            return
        App.get_running_app().encerrar_navegacao()

    def _cancelar_fim(self):
        self._confirmando_fim = False
        self.btn_encerrar.text = "Encerrar"

    # --- a cada leitura do GPS e a cada segundo -----------------------------------------
    def _ao_ler(self, vel):
        app = App.get_running_app()
        if vel is not None:
            self.disco.velo.velocidade = vel
            self.disco.velo.alerta = vel > app.ajustes["limite_kmh"]
        if app.posicao is not None and vel is not None:
            self.mapa.mostrar_eu(app.posicao[0], app.posicao[1], app.rumo_para_mapa(),
                                 app.precisao, vel)
        if self.estado == NAVEGANDO and app.estado_nav:
            self._atualizar_navegacao(app.estado_nav)
        elif self.estado == LIVRE and app.viagem.estado != Viagem.PARADA:
            agora = Clock.get_boottime()
            if agora - self._t_trilha >= TRILHA_A_CADA_S:
                self._t_trilha = agora
                self.mapa.definir_trilha([(p[0], p[1]) for p in app.viagem.pontos])
        self._atualizar_viagem()

    def _tique(self, dt):
        app = App.get_running_app()
        cor, texto = app.resumo_gps()
        self.ponto.cor = cor
        self.lbl_gps.text = texto
        if not app.sinal_ok():
            self.disco.velo.velocidade = 0
            self.disco.velo.alerta = False
        self._atualizar_viagem()

    def _atualizar_navegacao(self, e):
        m = e["manobra"]
        if m is not None:
            if m.get("indice") != self._manobra_vista:
                # manobra nova: o cartão "acende" e o conteúdo entra (chama o olho na hora certa)
                primeira, self._manobra_vista = self._manobra_vista is None, m.get("indice")
                if not primeira:
                    for w in (self.icone, self.lbl_dist, self.lbl_instr, self.lbl_rua):
                        Animation.cancel_all(w, "opacity")
                        w.opacity = 0.0
                        Animation(opacity=1.0, d=0.35, t="out_quad").start(w)
                    Animation.cancel_all(self.faixa, "cor_borda")
                    self.faixa.cor_borda = list(tema.VERDE)
                    Animation(cor_borda=list(tema.CIANO), d=0.9, t="out_quad").start(self.faixa)
            self.icone.acao = m["acao"]
            self.icone.saida = m.get("saida") or 0
            self.lbl_dist.text = fmt_dist_nav(e["dist_manobra"])
            self.lbl_instr.text = texto_manobra(m["acao"], m.get("saida"))
            self.lbl_rua.text = m["ruas"] or ""
        if e["fora_da_rota"]:
            app = App.get_running_app()
            self.lbl_instr.text = "Recalculando a rota..." if app.recalculando else "Fora da rota"
        self.col_tempo_nav.valor.text = fmt_duracao(e["restante_s"])
        self.col_tempo_nav.rotulo.text = "às %s" % fmt_hora_chegada(e["restante_s"])
        self.col_falta.valor.text = fmt_dist_nav(e["restante_m"])
        self.col_sobe.valor.text = "+%d m" % e["subida_restante_m"]
        # "Depois" e subida aparecem só quando existem
        depois, s = e["depois"], e["subida"]
        if depois is not None:
            self.icone_depois.acao = depois["acao"]
            self.icone_depois.saida = depois.get("saida") or 0
        if s is not None:
            nome = "Subida" if s["tipo"] == "subida" else "Descida"
            cor = tema.LARANJA if s["tipo"] == "subida" else tema.CIANO
            self.lbl_subida.color = cor
            self.chip_subida.cor_borda = cor
            if s["em_m"] > 0:
                self.lbl_subida.text = "%s de %d%% em %s" % (nome, round(s["grau"]), fmt_dist_nav(s["em_m"]))
            else:
                self.lbl_subida.text = "%s %d%%  |  faltam %s" % (nome, round(s["grau"]),
                                                                  fmt_dist_nav(s["falta_m"]))
        a = e.get("alerta")
        if a is not None:
            self.lbl_alerta.text = "%s em %s" % ("Semáforo" if a["tipo"] == "semaforo" else "Lombada",
                                                 fmt_dist_nav(a["em_m"]))
            self.chip_alerta.cor_borda = tema.VERMELHO if a["tipo"] == "semaforo" else tema.LARANJA
        tem = (depois is not None, s is not None, a is not None)
        if tem != (self._tem_depois, self._tem_subida, self._tem_alerta):
            self._tem_depois, self._tem_subida, self._tem_alerta = tem
            self._montar()
