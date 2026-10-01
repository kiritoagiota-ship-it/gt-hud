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

import tema
from falas import texto_manobra
from util import fmt_dist, fmt_dist_nav, fmt_duracao, fmt_hora_chegada, fmt_tempo
from viagem import Viagem
from widgets.botao import BotaoHUD
from widgets.comuns import PainelHUD, Ponto, Texto
from widgets.manobra import IconeManobra
from widgets.mapa import MapaHUD
from widgets.perfil import PerfilAltimetria
from widgets.velocimetro import Velocimetro

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
            Color(*tema.com_alfa(tema.FUNDO, 0.9))
            Ellipse(pos=self.pos, size=self.size)
            Color(*tema.CIANO_APAGADO)
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


class Coluna(BoxLayout):
    """Número grande com rótulo pequeno embaixo (barras de baixo)."""

    def __init__(self, rotulo, **kw):
        kw.setdefault("orientation", "vertical")
        super().__init__(**kw)
        self.valor = Texto(text="-", font_size=sp(22), bold=True, halign="center")
        self.rotulo = Texto(text=rotulo, font_size=tema.T_ROTULO, color=tema.CIANO_FRACO,
                            halign="center", size_hint_y=0.6)
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

        # --- velocímetro e botões do mapa ---
        self.disco = DiscoVelocimetro()
        self.btn_centro = BotaoHUD(text="Centralizar", font_size=tema.T_ROTULO + 1, opaco=True,
                                   size_hint=(None, None), on_release=lambda *a: self.mapa.recentralizar())
        self.btn_mais = BotaoHUD(text="+", size_hint=(None, None), opaco=True,
                                 on_release=lambda *a: self.mapa.mudar_zoom(1))
        self.btn_menos = BotaoHUD(text="-", size_hint=(None, None), opaco=True,
                                  on_release=lambda *a: self.mapa.mudar_zoom(-1))
        self.lbl_msg = Texto(text="", font_size=tema.T_ROTULO + 1, halign="center",
                             size_hint=(None, None))

        # --- barra de baixo: livre (viagem) ---
        self.barra_livre = PainelHUD(size_hint=(None, None))
        self.col_dist = Coluna("Distancia")
        self.col_tempo = Coluna("Tempo")
        self.controles = BoxLayout(spacing=dp(8), size_hint_x=1.6)
        for w in (self.col_dist, self.col_tempo, self.controles):
            self.barra_livre.add_widget(w)

        # --- barra de baixo: navegando ---
        self.barra_nav = PainelHUD(size_hint=(None, None))
        self.col_tempo_nav = Coluna("chegada")
        self.col_falta = Coluna("faltam")
        self.col_sobe = Coluna("de subida")
        self.btn_encerrar = BotaoHUD(text="Encerrar", cor=tema.VERMELHO, font_size=tema.T_ROTULO + 2,
                                     size_hint_x=0.9, on_release=lambda *a: self._encerrar())
        for w in (self.col_tempo_nav, self.col_falta, self.col_sobe, self.btn_encerrar):
            self.barra_nav.add_widget(w)

        # --- prévia da rota ---
        self.card = PainelHUD(orientation="vertical", size_hint=(None, None), spacing=dp(6))
        self.lbl_destino = Texto(text="", font_size=tema.T_BOTAO + 1, bold=True, color=tema.CIANO,
                                 size_hint_y=None, height=dp(26))
        self.lbl_resumo = Texto(text="", font_size=tema.T_ROTULO + 2, size_hint_y=None, height=dp(22))
        self.perfil = PerfilAltimetria(size_hint_y=None, height=dp(64))
        botoes = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        botoes.add_widget(BotaoHUD(text="Cancelar", on_release=lambda *a: app.cancelar_previa()))
        self.btn_iniciar = BotaoHUD(text="Iniciar", destaque=True,
                                    on_release=lambda *a: app.iniciar_navegacao())
        botoes.add_widget(self.btn_iniciar)
        for w in (self.lbl_destino, self.lbl_resumo, self.perfil, botoes):
            self.card.add_widget(w)

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

    def on_leave(self, *a):
        if self._ev_tique is not None:
            self._ev_tique.cancel()
            self._ev_tique = None

    # --- modos (chamados pelo app) -----------------------------------------------
    def modo_livre(self, mensagem=None, cor=None):
        self.estado = LIVRE
        self._tem_depois = self._tem_subida = False
        self.mapa.modo_navegacao(False)
        self.mapa.definir_rota([])
        self.mapa.definir_destino(None)
        self.mapa.recentralizar()
        self._montar()
        if mensagem:
            self.mensagem(mensagem, cor or tema.VERDE)

    def previa_calculando(self, lugar):
        self.estado = PREVIA
        self.lbl_destino.text = lugar["nome"]
        self.lbl_resumo.text = "Calculando a rota..."
        self.lbl_resumo.color = tema.CIANO_FRACO
        self.perfil.elevacao = []
        self.btn_iniciar.disabled = True
        self.mapa.definir_destino((lugar["lat"], lugar["lon"]))
        self._montar()

    def mostrar_previa(self, rota):
        self.estado = PREVIA
        n = len(rota.subidas)
        self.lbl_resumo.text = "%s  |  %s  |  sobe %d m  |  %d %s" % (
            fmt_dist_nav(rota.total_m), fmt_duracao(rota.tempo_s), rota.subida_total_m,
            n, "subida" if n == 1 else "subidas")
        self.lbl_resumo.color = tema.BRANCO
        self.perfil.subidas = rota.subidas
        self.perfil.elevacao = rota.elevacao
        self.btn_iniciar.disabled = False
        self.mapa.definir_rota(rota.pontos)
        self.mapa.definir_destino(rota.pontos[-1])
        self._montar()
        Clock.schedule_once(lambda dt: self.mapa.enquadrar(rota.pontos, dp(36), self._cobertos_previa()))

    def previa_erro(self, texto):
        self.lbl_resumo.text = texto
        self.lbl_resumo.color = tema.VERMELHO
        self.btn_iniciar.disabled = True

    def modo_navegando(self, rota):
        self.estado = NAVEGANDO
        self._tem_depois = self._tem_subida = False
        self._confirmando_fim = False
        self.btn_encerrar.text = "Encerrar"
        self.mapa.definir_rota(rota.pontos)
        self.mapa.definir_destino(rota.pontos[-1])
        self.mapa.modo_navegacao(True)
        self._montar()

    def trocar_rota(self, rota):
        self.mapa.definir_rota(rota.pontos)

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
        if self.estado == LIVRE:
            visiveis += [self.busca, self.status, self.menu, self.barra_livre]
        elif self.estado == PREVIA:
            visiveis += [self.status, self.card]
            visiveis.remove(self.disco)
        else:
            visiveis += [self.faixa, self.barra_nav]
            if self._tem_depois:
                visiveis.append(self.depois)
            if self._tem_subida:
                visiveis.append(self.chip_subida)
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
        self.busca.pos, self.busca.size = (m, topo - dp(54)), (larg_topo, dp(54))
        larg_menu = 3 * dp(74) + 2 * dp(6)
        self.menu.pos, self.menu.size = (W - m - larg_menu, topo - dp(54) - m - dp(40)), (larg_menu, dp(40))
        self.status.x = m
        self.status.topo_alvo = topo - dp(54) - m
        self.status.largura_max = W - 3 * m - larg_menu
        self.faixa.pos, self.faixa.size = (m, topo - dp(132)), (larg_topo, dp(132))
        self.depois.pos, self.depois.size = (m, topo - dp(132) - dp(6) - dp(38)), (dp(118), dp(38))
        larg_chip = min(larg_topo, dp(330))
        y_chip = topo - dp(132) - dp(6) - dp(44)
        if self._tem_depois:
            y_chip -= dp(44)
        self.chip_subida.pos, self.chip_subida.size = (m, y_chip), (larg_chip, dp(44))
        if self.estado == PREVIA:
            self.status.topo_alvo = topo
            self.status.largura_max = W - 2 * m

        # prévia
        larg_card = min(W - 2 * m, dp(480))
        self.card.size = (larg_card, dp(212))
        self.card.pos = (W - m - larg_card, m) if deitada else (m, m)

        # botões do mapa (direita, acima da barra)
        base = m + alt_barra + m if self.estado != PREVIA else m + dp(212) + m
        if deitada and self.estado == PREVIA:
            base = m
        x_btn = W - m - dp(50) if not (deitada and self.estado == PREVIA) else W - larg_card - 2 * m - dp(50)
        self.btn_menos.pos, self.btn_menos.size = (x_btn, base), (dp(50), dp(46))
        self.btn_mais.pos, self.btn_mais.size = (x_btn, base + dp(52)), (dp(50), dp(46))
        self.btn_centro.pos = (x_btn + dp(50) - dp(128), base + 2 * dp(52))
        self.btn_centro.size = (dp(128), dp(46))

        # mensagem curta
        if deitada:
            self.lbl_msg.pos, self.lbl_msg.size = (bx, m + alt_barra + dp(4)), (bw, dp(36))
        else:
            self.lbl_msg.pos = (m + tam_velo + m, m + alt_barra + m)
            self.lbl_msg.size = (W - tam_velo - 3 * m - dp(60), dp(44))
        # crédito do OpenStreetMap: à esquerda da coluna de botões (não por baixo dela)
        self.mapa.credito_margem = (W - x_btn + m, base + dp(2) if self.estado != PREVIA else m)
        # nomes do mapa não vão para baixo dos painéis (ficavam escondidos)
        self.mapa.areas_cobertas = [(w.x, w.y, w.right, w.top) for w in self.raiz.children
                                    if w is not self.mapa and w is not self.lbl_msg]
        self.mapa._aplicar()

    # --- viagem (modo livre) --------------------------------------------------------
    def _montar_controles(self):
        v = App.get_running_app().viagem
        c = self.controles
        c.clear_widgets()
        if v.estado == Viagem.PARADA:
            c.add_widget(BotaoHUD(text="Gravar viagem", font_size=tema.T_ROTULO + 2,
                                  on_release=lambda *a: self._viagem("iniciar")))
        elif v.estado == Viagem.GRAVANDO:
            c.add_widget(BotaoHUD(text="Pausar", font_size=tema.T_ROTULO + 2,
                                  on_release=lambda *a: self._viagem("pausar")))
            c.add_widget(BotaoHUD(text="Fim", cor=tema.LARANJA, font_size=tema.T_ROTULO + 2,
                                  on_release=lambda *a: self._viagem("finalizar")))
        else:
            c.add_widget(BotaoHUD(text="Retomar", destaque=True, font_size=tema.T_ROTULO + 2,
                                  on_release=lambda *a: self._viagem("retomar")))
            c.add_widget(BotaoHUD(text="Fim", cor=tema.LARANJA, font_size=tema.T_ROTULO + 2,
                                  on_release=lambda *a: self._viagem("finalizar")))
        self._estado_viagem = v.estado

    def _viagem(self, acao):
        app = App.get_running_app()
        if acao == "iniciar":
            app.viagem.iniciar()
            self.mensagem("Gravando viagem", tema.CIANO)
        elif acao == "pausar":
            app.viagem.pausar()
            self.mensagem("Viagem pausada", tema.LARANJA)
        elif acao == "retomar":
            app.viagem.retomar()
            self.mensagem("Gravando viagem", tema.CIANO)
        else:
            if app.salvar_viagem_atual():
                self.mensagem("Viagem salva: %s" % fmt_dist(app.ultima_salva_m))
            else:
                self.mensagem("Viagem com menos de 20 m: nao foi salva", tema.LARANJA)
            self.mapa.definir_trilha([])
        self._montar_controles()
        self._atualizar_viagem()

    def _atualizar_viagem(self):
        v = App.get_running_app().viagem
        self.col_dist.valor.text = fmt_dist(v.distancia_m)
        self.col_tempo.valor.text = fmt_tempo(v.tempo_total_s)
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
            self.icone.acao = m["acao"]
            self.icone.saida = m.get("saida") or 0
            self.lbl_dist.text = fmt_dist_nav(e["dist_manobra"])
            self.lbl_instr.text = texto_manobra(m["acao"], m.get("saida"))
            self.lbl_rua.text = m["ruas"] or ""
        if e["fora_da_rota"]:
            app = App.get_running_app()
            self.lbl_instr.text = "Recalculando a rota..." if app.recalculando else "Fora da rota"
        self.col_tempo_nav.valor.text = fmt_duracao(e["restante_s"])
        self.col_tempo_nav.rotulo.text = "chegada %s" % fmt_hora_chegada(e["restante_s"])
        self.col_falta.valor.text = fmt_dist_nav(e["restante_m"])
        self.col_sobe.valor.text = "+%d m" % e["subida_restante_m"]
        # "Depois" e subida aparecem só quando existem
        depois, s = e["depois"], e["subida"]
        if depois is not None:
            self.icone_depois.acao = depois["acao"]
            self.icone_depois.saida = depois.get("saida") or 0
        if s is not None:
            if s["em_m"] > 0:
                self.lbl_subida.text = "Subida de %d%% em %s" % (round(s["grau"]), fmt_dist_nav(s["em_m"]))
            else:
                self.lbl_subida.text = "Subida %d%%  |  faltam %s" % (round(s["grau"]), fmt_dist_nav(s["falta_m"]))
        if (depois is not None, s is not None) != (self._tem_depois, self._tem_subida):
            self._tem_depois, self._tem_subida = depois is not None, s is not None
            self._montar()
