"""Mapa do GT-HUD: mapa VETORIAL desenhado pelo próprio app (dados do
OpenFreeMap, preparados em mapa_vetor.py), rota, trilha, destino e a seta
de quem está pedalando.

- Coordenadas "locais": pixels do Web Mercator no zoom 14, menos uma origem
  fixa, Y para cima. Mexer no mapa (arrastar, seguir, girar, zoom) só muda
  4 instruções de matriz; a geometria dos tiles é feita uma vez por zoom
  inteiro de desenho ("rz") e, entre um inteiro e outro, só é ampliada.
- Ao trocar de rz, o desenho velho fica na tela até o novo chegar (nada de
  tela preta piscando).
- Nomes (ruas, bairros, lugares) são desenhados em coordenadas de TELA, de
  pé mesmo com o mapa girando, escolhidos para não se sobreporem.
- Toque: arrastar com inércia, pinça (zoom no ponto entre os dedos), duplo
  toque e rodinha do mouse com zoom suave.
- Fluidez: o GPS dá 1 posição por segundo. A seta não espera a próxima: anda
  sozinha pela velocidade (navegando, EM CIMA da rota: Navegacao.prever) e
  corrige suave quando a leitura chega; a câmera vai junto, sem atraso.
  Trabalho pesado na thread da tela (montar tiles, desenhar nomes) tem
  limite por quadro: o resto fica para os quadros seguintes.

A 1ª versão usava imagens prontas do OpenStreetMap pintadas por shader:
ficava ilegível no celular (nome pequeno, embaçado no zoom).
"""
import collections
import math
import time

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.animation import Animation
from kivy.graphics import (Color, Ellipse, InstructionGroup, Line, Mesh, PopMatrix,
                           PushMatrix, Rectangle, Rotate, RoundedRectangle, Scale, Translate)
from kivy.metrics import Metrics, dp, sp
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import busca
import goiania
import rede
import tema
from diagnostico import seguro
from widgets import icones_mapa
from widgets.mapa_camadas import CORES_TRANSITO, LINHA_LEVE, TOQUE_OCORRENCIA_DP, CamadasDoMapa

ATRASO_TOQUE_S = 0.15     # o cartão do ícone tocado abre depois disso: dá tempo de ver o ícone "pular"
from mapa_vetor import (AREAS, FUNDO, RUAS, FonteVetorial, chave_nome, ordem_das_linhas, legenda_se_precisa,
                        nivel_de_desenho, origem_padrao, tela_animando, tiles_do_retangulo, z_dados)

ZOOM_MIN, ZOOM_MAX = 11.0, 19.0   # o app é só de Goiânia: de longe, a cidade inteira
SEGURAR_S = 0.6                  # dedo parado esse tempo = marcar o ponto
TAM = 256.0
MAX_ROTULOS_RUA = 30
MAX_ROTULOS_LUGAR = 8
MAX_ROTULOS_POI = 14
# nome de avenida (secundária para cima) dentro de uma plaquinha azul com letra branca, como
# placa de rua (pedido do dono, 08/10/2026): escuro, claro
PLACA_ESCURO, PLACA_CLARO = (0.085, 0.270, 0.540, 0.93), (0.130, 0.370, 0.680, 0.95)
PESO_PLACA = 5             # _IMPORTANCIA a partir da qual o nome ganha placa (secundária, primária, expressa)
RASTRO_PONTOS = 18         # o rastro curto atrás da seta
RASTRO_PASSO_M = 6.0
DIST_NOME_DP = 15          # do centro do emblema do lugar até o começo do nome
# cor da bolinha de cada tipo de lugar (o nome sai num tom mais claro da mesma cor)
CORES_POI = {
    "praca": (0.40, 0.90, 0.55, 1), "comida": (1.0, 0.62, 0.25, 1), "compras": (1.0, 0.86, 0.35, 1),
    "saude": (1.0, 0.45, 0.50, 1), "ensino": (0.50, 0.76, 1.0, 1), "servico": (0.78, 0.68, 1.0, 1),
    "lazer": (0.55, 0.88, 0.88, 1), "outros": (0.75, 0.78, 0.82, 1),
}
REPOSICIONAR_S = 0.45      # refaz a escolha dos nomes no máximo a cada isso
INERCIA = 3.5              # quanto maior, mais rápido o deslize para
BONUS_JA_NA_TELA = 1.5     # nome já mostrado tem preferência: não fica trocando
MAX_TEXTURAS = 400
VOLTA_A_SEGUIR_S = 10.0    # navegando: depois de mexer no mapa, volta a seguir sozinho
MAX_PREVER_S = 1.5         # sem leitura nova do GPS, a seta para de andar sozinha depois disso
SUAVE_POS = 10.0           # rapidez da seta corrigindo para a posição nova (1/s)
SUAVE_CAMERA = 12.0        # rapidez da câmera indo atrás da seta (1/s)
SUAVE_GIRO = 4.0           # rapidez do mapa girando com a direção (1/s)
# zoom automático navegando: perto devagar, longe rápido. Fica dentro de UM
# nível de desenho (17): trocar de nível refaz o mapa inteiro da tela
ZOOM_NAV_PERTO, ZOOM_NAV_LONGE = 17.4, 16.6
HISTERESE_ZOOM = 0.75      # só troca o nível de desenho com essa folga
ORCAMENTO_TILES_S = 0.006  # por quadro, no máximo isso montando tiles
# Mapa sem buraco (pedido do dono, 07/10/2026): de perto (zoom de desenho >= ZOOM_COM_FUNDO),
# enquanto o pedaço detalhado não fica pronto, aparece no lugar o mesmo pedaço no
# desenho do zoom RZ_FUNDO, esticado (ele já vem pronto dentro do app).
ZOOM_COM_FUNDO = 15
RZ_FUNDO = 14
ADIANTAR_POR_VEZ = 14      # pedaços vizinhos/de outros zooms pedidos "para depois" a cada vista nova
# animações da prévia da rota (pedido do dono, 07/10/2026: escolher um destino
# dava uma travada e o caminho aparecia seco)
RADAR_VOLTA_S = 1.7        # cada onda do "procurando caminho" leva isso
ZOOM_TOQUE_S = 0.28        # o zoom do toque duplo desliza por esse tempo
FESTA_S = 3.2              # ondas verdes no destino ao chegar
RADAR_MAX_S = 40.0         # sem resposta nesse tempo, o radar se apaga sozinho
PINO_CAI_S = 0.85          # o pino do destino caindo
BRILHO_S = 0.7             # clarão da rota quando termina de se desenhar
PONTOS_REVELAR = 160       # a rota se desenhando usa no máximo tantos pontos (leve a cada quadro)
MAX_TEXTURAS_NOVAS = 8     # por escolha de nomes, no máximo tantos nomes novos desenhados
# Lugares da base da busca (69.900 em Goiânia) desenhados no mapa: o mapa do
# OpenStreetMap tem pouco comércio cadastrado na cidade. Só de perto, e
# quanto mais perto, mais lugares (pela "confiança" da base).
ZOOM_LUGARES = 16.5
CONF_POR_ZOOM = ((18.3, 0.75), (17.5, 0.86), (16.5, 0.94))   # (zoom mínimo, confiança mínima)
MAX_CELULAS_LUGARES = 24


def mundo(lat, lon, z):
    n = TAM * 2.0 ** z
    lat = max(-85.0, min(85.0, lat))
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def geo(x, y, z):
    n = TAM * 2.0 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    return lat, lon


def metros_por_px(lat, z):
    return 156543.03392 * math.cos(math.radians(lat)) / (2.0 ** z)


def _girar(x, y, graus):
    a = math.radians(graus)
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def _dif_angulo(de, para):
    return (para - de + 180.0) % 360.0 - 180.0


class _Rotulo:
    """Um nome desenhado na tela (posição/ângulo atualizados a cada quadro).
    Lugar (ponto != None) ganha o emblema da categoria antes do nome, e os
    dois surgem com um pequeno "pulo" (não aparecem do nada)."""

    def __init__(self, info, textura, ponto=None, placa=None):
        self.info = info
        self.textura = textura
        self.placa = placa
        self.grupo = InstructionGroup()
        self.bolinha = None
        self.grupo.add(PushMatrix())
        self.mover = Translate(0, 0)
        self.girar = Rotate(angle=0, axis=(0, 0, 1))
        self.grupo.add(self.mover)
        self.grupo.add(self.girar)
        w, h = textura.size
        deslocar = -w / 2.0
        if ponto is not None:
            self.icone = icones_mapa.qual_icone(info.get("grupo"), info.get("texto"))
            self.grupo.add(PushMatrix())
            self.cresce = Scale(0.2, 0.2, 1)
            self.grupo.add(self.cresce)
            self.grupo.add(icones_mapa.emblema(self.icone, ponto, FUNDO))
            self.grupo.add(PopMatrix())
            Animation(x=1.0, y=1.0, d=0.26, t="out_back").start(self.cresce)
            deslocar = dp(DIST_NOME_DP)
        if placa is not None:   # nome de avenida: dentro de uma plaquinha, como placa de rua
            self.cor_placa = Color(placa[0], placa[1], placa[2], 0.0)
            self.grupo.add(self.cor_placa)
            self.grupo.add(RoundedRectangle(pos=(deslocar - dp(7), -h / 2.0 - dp(1.5)),
                                            size=(w + dp(14), h + dp(3)), radius=[dp(5)]))
            Animation(a=placa[3], d=0.22, t="out_quad").start(self.cor_placa)
        self.cor = Color(1, 1, 1, 0.0)
        self.grupo.add(self.cor)
        self.grupo.add(Rectangle(texture=textura, size=(w, h), pos=(deslocar, -h / 2.0)))
        self.grupo.add(PopMatrix())
        Animation(a=1.0, d=0.22, t="out_quad").start(self.cor)
        self.caixa_nome = (deslocar, -h / 2.0, deslocar + w, h / 2.0)   # em volta do ponto: para o toque


class MapaHUD(CamadasDoMapa, Widget):
    zoom = NumericProperty(16.0)
    rotacao = NumericProperty(0.0)    # rumo (graus, horário a partir do norte) que fica para cima
    seguindo = BooleanProperty(True)  # a câmera acompanha quem pedala
    girar = BooleanProperty(True)     # no modo navegação, gira com a direção

    def __init__(self, pasta_cache, **kw):
        super().__init__(**kw)
        self.centro = (-16.6799, -49.2550)  # até o GPS responder: centro de Goiânia
        self.ancora = (0.5, 0.5)            # onde o centro fica na tela (frações)
        self.ancora_nav = (0.5, 0.30)       # navegando e girando (a tela muda isso deitada)
        self.eu = None                      # (lat, lon, rumo ou None, precisão m)
        self._navegando = False
        self._escala = Metrics.density      # px de tela por px do mundo no zoom 14
        self._origem = origem_padrao()      # fixo (centro de Goiânia): os pedaços prontos dependem dele
        self._rota, self._trilha, self._destino = [], [], None
        self._trechos = []                  # avenidas da rota: [(pontos, nível)]
        self._transito = []                 # trânsito de agora na rota: [(pontos, magnitude)]
        self._larg_rota = []
        self._alternativas = []
        self._desenhados = {}               # (dz, tx, ty, rz) -> [(grupo, instrução), ...]
        self._fundo_desenhado = {}          # (dz, tx, ty, RZ_FUNDO) -> instrução (o pedaço esticado)
        self._faltando = True               # ainda falta pedaço detalhado na vista de agora
        self._nivel = None                  # (dz, rz) atual
        self._rotulos = []
        self._texturas = collections.OrderedDict()
        self._lugares = collections.OrderedDict()   # (cx, cy) -> [rótulos] ou None (carregando)
        self._chave_tiles = None            # vista da última conta de tiles
        lat0, lon0, lat1, lon1 = goiania.LIMITES  # Goiânia em px do mundo z14
        x0, y0 = mundo(lat1, lon0, 14)
        x1, y1 = mundo(lat0, lon1, 14)
        self._caixa_goiania = (x0, y0, x1, y1)
        self._tiles_sujo = True
        self._t_mexeu = 0.0                 # time.time() do último toque no mapa
        self.areas_cobertas = []            # (x0, y0, x1, y1) tapados por painéis da tela
        self._t_rotulos = 0.0
        self._ev_rotulos = None
        self._larg_usada = None
        self._quadro = None
        self._fix = None                    # última leitura: (lat, lon, rumo, m/s, hora)
        self._vista = None                  # onde a seta está desenhada: (lat, lon, rumo)
        self.prever = None                  # navegando: Navegacao.prever (seta na linha)
        self.ativo = True                   # False quando a tela do mapa não está à vista
        self._em_lote = False
        self._rz = None
        self._novas_texturas = 0
        self._alvo_zoom = None
        self._ev_anim = None
        self._toques = []
        self._voo = None                    # câmera voando até um enquadramento
        self._rz_fixo = None                # no voo: já desenha no zoom de chegada
        self._revelar = None                # rota se desenhando do começo ao fim
        self._brilho = None                 # hora em que a rota acabou de se desenhar
        self._radar_t0 = None               # "procurando caminho": ondas saindo de quem pedala
        self._festa = None                  # chegada: (hora, (lat, lon)) das ondas verdes no destino
        self._destaque = None               # alerta chegando: ((lat, lon), cor) -> placa maior e anel pulsando
        self._salto = None                  # ícone tocado dando um pulo: (hora, (lat, lon))
        self._onda_toque = None             # ... e a onda que sai dele: (hora, (x, y) locais[, cor])
        self._zoom_toque = None             # toque duplo: o zoom deslizando até o nível seguinte
        self._dest_pousou = True            # o pino que está caindo já tocou o chão?
        self._curva = []                    # a seta da próxima curva, desenhada no chão: [(lat, lon)]
        self._rastro = collections.deque(maxlen=RASTRO_PONTOS)   # por onde a seta acabou de passar (locais)
        self._dest_t0 = None                # pino do destino caindo
        self.ao_segurar = None              # ao_segurar(lat, lon): dedo parado no mapa
        self.ocorrencias = []               # trânsito de Goiânia agora (transito.py), mesmo sem rota
        self._fluxo = []                    # ruas pela velocidade de agora: [(pontos locais, nível)]
        self._fluxo_rz = None               # nível de desenho em que a malha das cores foi feita
        self._ocorr_icones = []             # [(lat, lon, tipo do ícone, ocorrência)]
        self._ocorr_na_tela = []            # [(x local, y local, ocorrência)] com ícone à vista
        self._larg_geral = []               # linhas dos trechos lentos da cidade
        self.ao_tocar_ocorrencia = None     # ao_tocar_ocorrencia(ocorrência): toque no ícone
        self.ao_tocar_lugar = None          # ao_tocar_lugar({nome, legenda, icone, lat, lon}): toque num lugar
        self._ev_segurar = None
        self._velocidade = (0.0, 0.0)
        self._movs = []
        self.fonte = FonteVetorial(pasta_cache, self._origem, self._escala, Metrics.density,
                                   self._tile_pronto)

        with self.canvas:
            Color(*FUNDO)
            self._fundo = Rectangle()
            PushMatrix()
            self._m_ancora = Translate(0, 0)
            self._m_rot = Rotate(angle=0, axis=(0, 0, 1))
            self._m_esc = Scale(1, 1, 1)
            self._m_centro = Translate(0, 0)
        self._g_fundo = InstructionGroup()    # pedaços esticados que tapam buraco (por baixo de tudo)
        self.canvas.add(self._g_fundo)
        self._g_areas = InstructionGroup()
        self.canvas.add(self._g_areas)
        # córregos e trilhos, a borda das ruas, as pontes, as ruas (da menos importante para a
        # mais), o tracejado do meio das avenidas e as setas de mão única: nesta ordem
        self._g_ruas = {}
        for nome in ordem_das_linhas():
            self._g_ruas[nome] = InstructionGroup()
            self.canvas.add(self._g_ruas[nome])
        self._g_fluxo = InstructionGroup()      # ruas coloridas pela velocidade de agora
        self.canvas.add(self._g_fluxo)
        self._g_transito = InstructionGroup()   # trânsito da cidade: por cima das ruas, por baixo da rota
        self.canvas.add(self._g_transito)
        self._g_trilha = InstructionGroup()
        self._g_alt = InstructionGroup()      # outras rotas que dá para escolher (cinza)
        self._g_rota = InstructionGroup()
        self._g_rastro = InstructionGroup()   # rastro curto atrás da seta
        self._g_curva = InstructionGroup()    # seta da próxima curva, pintada no chão por cima da rota
        self.canvas.add(self._g_trilha)
        self.canvas.add(self._g_alt)
        self.canvas.add(self._g_rota)
        self.canvas.add(self._g_rastro)
        self.canvas.add(self._g_curva)
        self._rastro_linhas = []
        for alfa in (0.10, 0.22, 0.38):       # do pedaço mais velho para o mais novo
            self._g_rastro.add(Color(1, 1, 1, alfa))
            linha = Line(points=[0, 0, 0, 0], width=1, cap="round", joint="round", **LINHA_LEVE)
            self._g_rastro.add(linha)
            self._rastro_linhas.append(linha)
        self.canvas.add(PopMatrix())
        self._g_sinais = InstructionGroup()   # semáforos e lombadas (tela)
        self.canvas.add(self._g_sinais)
        self._sinais = []                     # [(x local, y local, Translate)]
        self._icones = {}                     # (lat, lon) -> (grupo, Translate)
        self.sinais_rota = None               # navegando: só os do caminho [(lat, lon, tipo)]
        self.marcos = []                      # pinos fixos: [(lat, lon, "casa"/"trabalho")]
        self._g_rotulos = InstructionGroup()  # nomes, em coordenadas de tela
        self.canvas.add(self._g_rotulos)
        self._g_tela = InstructionGroup()     # seta e destino
        self.canvas.add(self._g_tela)
        self._montar_marcas()

        # crédito exigido pelos dados
        self.credito = Label(text="(c) OpenStreetMap, OpenFreeMap", font_size=dp(10),
                             color=tema.CIANO_FRACO, size_hint=(None, None), size=(dp(170), dp(16)))
        self.add_widget(self.credito)
        self.credito_margem = (dp(6), dp(4))
        self.bind(pos=self._aplicar, size=self._aplicar, zoom=self._ao_mudar, rotacao=self._ao_mudar)

    def _ao_mudar(self, *a):
        if not self._em_lote:  # na animação, _aplicar roda uma vez só no fim do quadro
            self._aplicar()

    # --- API usada pelas telas ---------------------------------------------
    def mostrar_eu(self, lat, lon, rumo=None, precisao=None, vel_kmh=None):
        self.eu = (lat, lon, rumo, precisao)
        self._fix = (lat, lon, rumo, max(0.0, vel_kmh or 0.0) / 3.6, time.monotonic())
        if (self._navegando and not self.seguindo and not self._toques
                and time.time() - self._t_mexeu > VOLTA_A_SEGUIR_S):
            self.seguindo = True  # olhou o mapa e largou: volta para a seta
        if self.seguindo and self._navegando and vel_kmh is not None:
            # zoom automático: mais longe quando anda rápido
            f = max(0.0, min(1.0, (vel_kmh - 12.0) / 23.0))
            self._alvo_zoom = ZOOM_NAV_PERTO - f * (ZOOM_NAV_PERTO - ZOOM_NAV_LONGE)
        self._ligar_animacao()

    def recentralizar(self):
        self._cancelar_voo()
        self.seguindo = True
        self._ligar_animacao()

    def pausar(self):
        """Tela do mapa saiu de vista: nada de animar à toa."""
        self.ativo = False
        if self._ev_anim is not None:
            self._ev_anim.cancel()
            self._ev_anim = None

    def retomar(self):
        self.ativo = True
        self._aplicar()
        self._ligar_animacao()

    def modo_navegacao(self, ligado):
        self._cancelar_voo()
        self._radar_t0 = None
        self._navegando = ligado
        if not ligado:
            self._destaque = None
            self._curva = []
            self._g_curva.clear()
        # navegando e girando: a seta fica mais embaixo, sobra mapa à frente
        ancora = self.ancora_nav if (ligado and self.girar) else (0.5, 0.5)
        if ligado:
            self.seguindo = True
            self._alvo_zoom = ZOOM_NAV_PERTO
            # a câmera MERGULHA da vista da rota inteira até a seta, já girando para a
            # direção do caminho (antes o mapa pulava de uma vista para a outra)
            alvo = self._vista or (self.eu[:3] if self.eu else None)
            if alvo is not None and self.ativo and self.width > 2:
                giro = alvo[2] if (self.girar and alvo[2] is not None) else 0.0
                if self._voar((alvo[0], alvo[1]), ZOOM_NAV_PERTO, ancora, giro, 1.1):
                    return
            self.ancora = ancora
        else:
            self.ancora = ancora
            self._alvo_zoom = None
            self.prever = None
        self._aplicar()
        self._ligar_animacao()

    def definir_rota(self, pontos, animar=0.0):
        """animar = segundos para a linha se desenhar de quem pedala até o
        destino (0 = aparece inteira na hora)."""
        self._rota = list(pontos)
        self._trechos = []          # as avenidas eram da rota antiga
        self._transito = []
        self._revelar = self._brilho = None
        if animar > 0 and len(self._rota) >= 2 and self.ativo:
            passo = max(1, len(self._rota) // PONTOS_REVELAR)
            pts = [self._local(p[0], p[1]) for p in self._rota[::passo]]
            if (len(self._rota) - 1) % passo:
                pts.append(self._local(*self._rota[-1][:2]))
            ac = [0.0]
            for a, b in zip(pts, pts[1:]):
                ac.append(ac[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
            if ac[-1] > 0:
                self._revelar = {"t0": time.monotonic(), "dur": float(animar), "pts": pts, "ac": ac,
                                 "linhas": (), "ponta": pts[0]}
                self._ligar_animacao()
        self._refazer_linhas()

    def comemorar(self, onde=None):
        """Chegou: ondas verdes saem do destino por FESTA_S segundos."""
        onde = onde or self._destino or (self.eu[:2] if self.eu else None)
        if onde is None:
            return
        self._festa = (time.monotonic(), tuple(onde[:2]))
        self._ligar_animacao()

    def definir_seta_curva(self, pontos):
        """A próxima manobra desenhada no chão: uma seta branca larga por cima da
        rota, passando pela curva (pontos (lat, lon) de antes até depois dela).
        [] tira."""
        self._curva = list(pontos or [])
        self._desenhar_seta_curva()

    def _desenhar_seta_curva(self):
        self._g_curva.clear()
        if len(self._curva) < 2 or not self._navegando:
            return
        pts = [self._local(p[0], p[1]) for p in self._curva]
        s = self._escala_tela()
        # a ponta: um triângulo no fim, na direção do último trecho
        (ax, ay), (bx, by) = pts[-2], pts[-1]
        comp = math.hypot(bx - ax, by - ay) or 1.0
        ux, uy = (bx - ax) / comp, (by - ay) / comp
        t, meia = dp(15) / s, dp(11) / s
        ponta = [(bx + ux * t, by + uy * t), (bx - uy * meia, by + ux * meia), (bx + uy * meia, by - ux * meia)]
        plano = [c for p in pts for c in p]
        # (borda escura por baixo e o branco por cima; um pouco mais larga que a linha da rota)
        for cor, px, cresce in (((0.03, 0.05, 0.08, 0.85), dp(7.4), 1.3), ((1, 1, 1, 0.97), dp(5.2), 1.0)):
            self._g_curva.add(Color(*cor))
            self._g_curva.add(Line(points=plano, width=px / s, cap="round", joint="round", **LINHA_LEVE))
            cx, cy = sum(p[0] for p in ponta) / 3.0, sum(p[1] for p in ponta) / 3.0
            tri = [(cx + (x - cx) * cresce, cy + (y - cy) * cresce) for x, y in ponta]
            self._g_curva.add(Mesh(vertices=[v for x, y in tri for v in (x, y, 0, 0)], indices=[0, 1, 2],
                                   mode="triangles"))

    def procurar(self, ligado):
        """Calculando a rota: ondas de radar saem de quem pedala (e uma do
        destino) até a resposta chegar."""
        self._radar_t0 = time.monotonic() if ligado else None
        if ligado:
            self._ligar_animacao()
        else:
            self._desenhar_tela()

    def definir_trechos(self, trechos):
        """Trechos da rota em via movimentada [(pontos, nível)]: desenhados por
        cima da linha em laranja (movimentado) ou vermelho (pesado), para a
        pessoa ver ONDE o caminho pede mais atenção."""
        self._trechos = [(list(pontos), nivel) for pontos, nivel in trechos if len(pontos) >= 2]
        self._refazer_linhas()

    def definir_transito(self, trechos):
        """Trânsito de agora na rota [(pontos, magnitude 1..4)]: uma faixa larga
        POR BAIXO da linha (amarelo = lento, laranja = moderado, vermelho =
        parado, vinho = via interditada). A linha da rota segue por cima."""
        self._transito = [(list(pontos), m) for pontos, m in trechos if len(pontos) >= 2]
        self._refazer_linhas()

    def definir_alternativas(self, listas):
        """Rotas que a pessoa pode escolher em vez da atual (desenho cinza)."""
        self._alternativas = [list(p) for p in listas]
        self._refazer_linhas()

    def definir_trilha(self, pontos):
        self._trilha = list(pontos)
        self._refazer_linhas(so_trilha=True)

    def definir_destino(self, lat_lon, cair=False):
        """cair=True: o pino desce e \"quica\" no lugar (destino recém-escolhido)."""
        self._destino = lat_lon
        self._dest_t0 = time.monotonic() if (cair and lat_lon) else None
        self._dest_pousou = self._dest_t0 is None
        if self._dest_t0 is not None:
            self._ligar_animacao()
        self._desenhar_tela()

    def enquadrar(self, pontos, margem_px=None, cobertos=(0, 0, 0, 0), animado=False, duracao=0.9):
        """Mostra todos os pontos (norte para cima), sem seguir quem pedala.
        `cobertos` = (esquerda, baixo, direita, cima) em px tapados por
        painéis: a rota cabe no pedaço de mapa que sobra visível.
        animado=True: a câmera VOA até lá em `duracao` segundos."""
        if not pontos or self.width < 2 or self.height < 2:
            return
        margem = margem_px if margem_px is not None else dp(60)
        esq, baixo, dir_, cima = cobertos
        lats = [p[0] for p in pontos]
        lons = [p[1] for p in pontos]
        x0, y0 = mundo(max(lats), min(lons), 0)
        x1, y1 = mundo(min(lats), max(lons), 0)
        meio = geo((x0 + x1) / 2.0, (y0 + y1) / 2.0, 0)
        livre_w = max(self.width - esq - dir_, 20)
        livre_h = max(self.height - baixo - cima, 20)
        larg = max((livre_w - 2 * margem) / self._escala, 10)
        alt = max((livre_h - 2 * margem) / self._escala, 10)
        z = 14 + math.log2(min(larg / max((x1 - x0) * 2 ** 14, 1e-9),
                               alt / max((y1 - y0) * 2 ** 14, 1e-9)))
        self.seguindo = False
        ancora = ((esq + livre_w / 2.0) / max(self.width, 1),
                  (baixo + livre_h / 2.0) / max(self.height, 1))
        zoom = max(ZOOM_MIN, min(17.0, z))
        self._cancelar_voo()
        if animado and self.ativo:
            self._alvo_zoom = None
            if self._voar(meio, zoom, ancora, 0.0, duracao):
                return
        self._parar_animacao()
        self.ancora = ancora
        self.centro = meio
        self.rotacao = 0.0
        self.zoom = zoom
        self._aplicar()
        if self._radar_t0 is not None or self._revelar is not None or self._dest_t0 is not None:
            self._ligar_animacao()

    def _voar(self, centro, zoom, ancora, giro, duracao):
        """A câmera voa até (centro, zoom, âncora, giro). False se já está lá."""
        de, para = self._local(*self.centro), self._local(*centro)
        s = self._escala_tela()
        perto = (abs(zoom - self.zoom) < 0.04 and math.hypot(para[0] - de[0], para[1] - de[1]) * s < dp(6)
                 and abs(ancora[0] - self.ancora[0]) + abs(ancora[1] - self.ancora[1]) < 0.01
                 and abs(_dif_angulo(self.rotacao, giro)) < 2.0)
        if perto:
            return False
        self._velocidade = (0.0, 0.0)
        self._voo = {"t0": time.monotonic(), "dur": max(0.05, duracao),
                     "de": (de, self.zoom, self.ancora, self.rotacao),
                     "para": (para, zoom, ancora), "centro": centro, "giro": giro % 360.0}
        # já desenha (e pede) o mapa no zoom de CHEGADA: os pedaços do zoom
        # atual ficam na tela, esticados, até os novos cobrirem tudo
        self._rz_fixo = nivel_de_desenho(zoom)
        self._pedir_tiles_de(para, zoom, ancora)
        self._ligar_animacao()
        return True

    def _cancelar_voo(self):
        self._voo = None
        self._rz_fixo = None

    def preaquecer(self, largura, altura):
        """Na abertura do app (a tela do mapa ainda nem apareceu): já pede os
        pedaços do mapa de onde a pessoa estava da última vez, no zoom em que
        o mapa abre. Quando a abertura termina, o mapa está na tela."""
        rz = nivel_de_desenho(self.zoom)
        self._pedir_tiles_de(self._local(*self.centro), self.zoom, self.ancora, rz, largura, altura)

    def _pedir_tiles_de(self, centro_local, zoom, ancora, rz=None, largura=None, altura=None):
        """Pede já o preparo dos pedaços do mapa de uma vista que AINDA não é a
        da tela (a chegada do voo da câmera, a abertura do app), norte para
        cima: quando a câmera chega, o mapa está pronto ou quase."""
        rz = self._rz_fixo if rz is None else rz
        largura = self.width if largura is None else largura
        altura = self.height if altura is None else altura
        dz = z_dados(rz)
        s = self._escala * 2.0 ** (zoom - 14)
        cx, cy = centro_local
        ax, ay = largura * ancora[0], altura * ancora[1]
        margem = dp(40)
        x0 = cx + (-margem - ax) / s + self._origem[0]
        x1 = cx + (largura + margem - ax) / s + self._origem[0]
        y0 = self._origem[1] - (cy + (altura + margem - ay) / s)
        y1 = self._origem[1] - (cy + (-margem - ay) / s)
        gx0, gy0, gx1, gy1 = self._caixa_goiania
        lado = 256.0 * 2 ** (14 - dz)
        mx, my = (cx + self._origem[0]) / lado, (self._origem[1] - cy) / lado
        tiles = tiles_do_retangulo(max(x0, gx0), max(y0, gy0), min(x1, gx1), min(y1, gy1), dz)
        # a fila atende o pedido mais recente primeiro: os do meio são pedidos por último
        for tx, ty in sorted(tiles, key=lambda c: -((c[0] + 0.5 - mx) ** 2 + (c[1] + 0.5 - my) ** 2))[-40:]:
            chave = (dz, tx, ty, rz)
            if chave not in self._desenhados:
                self.fonte.pedir(chave)
                if rz >= ZOOM_COM_FUNDO:   # (pedido por último = feito primeiro: é rápido e tapa o buraco)
                    self.fonte.pedir((dz, tx, ty, RZ_FUNDO))

    def ao_voltar(self):
        """App voltou do segundo plano: no Android as texturas dos nomes podem
        ter se perdido junto com o contexto gráfico; refaz."""
        self._texturas.clear()
        self._g_rotulos.clear()
        self._rotulos = []
        self._tiles_sujo = True
        self._t_rotulos = 0.0
        self._aplicar()

    def mudar_zoom(self, delta, animado=True):
        self._zoom_toque = None
        alvo = max(ZOOM_MIN, min(ZOOM_MAX, (self._alvo_zoom or self.zoom) + delta))
        if animado:
            self._alvo_zoom = alvo
            self._ligar_animacao()
        else:
            self.zoom = alvo

    # --- conversões -----------------------------------------------------------
    def _local(self, lat, lon):
        x, y = mundo(lat, lon, 14)
        return x - self._origem[0], self._origem[1] - y

    def _escala_tela(self):
        return self._escala * 2.0 ** (self.zoom - 14)

    def _ancora_px(self):
        return self.x + self.width * self.ancora[0], self.y + self.height * self.ancora[1]

    def _local_para_tela(self, lx, ly):
        q = self._quadro
        if q is None:
            q = self._medir_quadro()
        cx, cy, s, ax, ay, c, sn = q
        dx, dy = (lx - cx) * s, (ly - cy) * s
        return ax + dx * c - dy * sn, ay + dx * sn + dy * c

    def _medir_quadro(self):
        """Centro, escala, âncora e giro do quadro atual (calculados uma vez:
        os nomes e a seta usam a cada quadro da animação)."""
        cx, cy = self._local(*self.centro)
        ax, ay = self._ancora_px()
        a = math.radians(self.rotacao)
        self._quadro = (cx, cy, self._escala_tela(), ax, ay, math.cos(a), math.sin(a))
        return self._quadro

    def _tela_para_local(self, sx, sy):
        self._quadro = None
        ax, ay = self._ancora_px()
        dx, dy = _girar(sx - ax, sy - ay, -self.rotacao)
        cx, cy = self._local(*self.centro)
        s = self._escala_tela()
        return cx + dx / s, cy + dy / s

    def _para_tela(self, lat, lon):
        return self._local_para_tela(*self._local(lat, lon))

    def _local_para_geo(self, lx, ly):
        return geo(lx + self._origem[0], self._origem[1] - ly, 14)

    # --- desenho ----------------------------------------------------------------
    @seguro  # erro no desenho do mapa nunca fecha o app (fica no diagnóstico)
    def _aplicar(self, *a):
        if self.width < 2 or self.height < 2:
            return
        self._quadro = None
        q = self._medir_quadro()
        self._fundo.pos, self._fundo.size = self.pos, self.size
        self.credito.pos = (self.right - self.credito.width - self.credito_margem[0],
                            self.y + self.credito_margem[1])
        cx, cy, s, ax, ay = q[:5]
        self._m_ancora.xy = (ax, ay)
        self._m_rot.angle = self.rotacao
        self._m_esc.xyz = (s, s, 1)
        self._m_centro.xy = (-cx, -cy)
        self._atualizar_tiles()
        self._ajustar_larguras(s)
        self._mover_rotulos()
        self._desenhar_tela()
        self._pedir_rotulos()

    def _nivel_desenho(self):
        """Zoom inteiro de desenho, com folga: na pinça ou no zoom automático
        o mapa não fica sendo refeito a cada vez que passa de x,5."""
        if self._rz_fixo is not None:
            self._rz = self._rz_fixo
        elif self._rz is None or abs(self.zoom - self._rz) > HISTERESE_ZOOM:
            self._rz = nivel_de_desenho(self.zoom)
        return self._rz

    def _atualizar_tiles(self):
        rz = self._nivel_desenho()
        dz = z_dados(rz)
        nivel = (dz, rz)
        # na animação isto roda 60x/s: só refaz a conta quando a vista andou
        # um pedaço (menos que a margem de dp(40) além da borda da tela)
        cx, cy = self._local(*self.centro)
        s = self._escala_tela()
        passo = dp(24)
        vista = (nivel, int(cx * s // passo), int(cy * s // passo), int(self.zoom * 20),
                 int(self.rotacao // 3), self.x, self.y, self.width, self.height, self.ancora)
        if vista == self._chave_tiles and not self._tiles_sujo:
            return
        self._chave_tiles, self._tiles_sujo = vista, False
        xs, ys = [], []
        margem = dp(40)
        for px, py in ((self.x - margem, self.y - margem), (self.right + margem, self.y - margem),
                       (self.x - margem, self.top + margem), (self.right + margem, self.top + margem)):
            lx, ly = self._tela_para_local(px, py)
            xs.append(lx + self._origem[0])
            ys.append(self._origem[1] - ly)
        gx0, gy0, gx1, gy1 = self._caixa_goiania
        precisa = {(dz, tx, ty, rz) for tx, ty in tiles_do_retangulo(
            max(min(xs), gx0), max(min(ys), gy0), min(max(xs), gx1), min(max(ys), gy1), dz)}
        # do centro para fora: o que está no meio da tela chega primeiro
        lado = 256.0 * 2 ** (14 - dz)
        mx, my = (cx + self._origem[0]) / lado, (self._origem[1] - cy) / lado
        faltando = adiado = False
        t0 = time.perf_counter()
        pedir = []
        for chave in sorted(precisa, key=lambda c: (c[1] + 0.5 - mx) ** 2 + (c[2] + 0.5 - my) ** 2):
            if chave in self._desenhados:
                continue
            preparado = self.fonte.pronto(chave)
            if preparado is None:
                pedir.append(chave)
                faltando = True
            elif time.perf_counter() - t0 > ORCAMENTO_TILES_S:
                faltando = adiado = True  # monta no próximo quadro (sem tranco)
            else:
                self._desenhar_tile(chave, preparado)
        # a fila atende o pedido MAIS RECENTE primeiro: pede de fora para dentro (o do
        # meio da tela por último) e, depois de todos, os de fundo (rápidos; tapam o buraco)
        for chave in reversed(pedir):
            self.fonte.pedir(chave)
        com_fundo = rz >= ZOOM_COM_FUNDO
        quer_fundo = set()
        if com_fundo:
            for chave in precisa:
                if chave not in self._desenhados:
                    quer_fundo.add((chave[0], chave[1], chave[2], RZ_FUNDO))
            for chave in sorted(quer_fundo, key=lambda c: -((c[1] + 0.5 - mx) ** 2 + (c[2] + 0.5 - my) ** 2)):
                if chave in self._fundo_desenhado:
                    continue
                preparado = self.fonte.pronto(chave)
                if preparado is None:
                    self.fonte.pedir(chave)
                else:
                    self._desenhar_fundo(chave, preparado)
        for chave in [c for c in self._fundo_desenhado if c not in quer_fundo]:
            self._g_fundo.remove(self._fundo_desenhado.pop(chave))   # o detalhado chegou (ou saiu da tela)
        if adiado:
            self._tiles_sujo = True
            Clock.schedule_once(lambda dt: self._aplicar(), 0)
        self._faltando = faltando
        if not adiado and not faltando:
            self._adiantar(precisa, dz, rz, (min(xs), min(ys), max(xs), max(ys)))
        for chave in list(self._desenhados):
            mesmo_nivel = (chave[0], chave[3]) == nivel
            # desenho de outro zoom só sai quando o novo já cobriu a tela
            if (mesmo_nivel and chave not in precisa) or (not mesmo_nivel and not faltando):
                self._apagar_tile(chave)
        if nivel != self._nivel:
            self._nivel = nivel
            self._t_rotulos = 0.0
        self._desenhar_fluxo()   # (só refaz se o nível de desenho ou a visibilidade mudou)

    def _adiantar(self, precisa, dz, rz, caixa):
        """A tela está completa: deixa prontos (sem pressa, quando a fila do
        mapa estiver livre) os pedaços vizinhos e os da mesma vista um zoom
        para dentro e um para fora. Arrastar e dar zoom já acham o mapa pronto."""
        if self.fonte.ocupada():
            return
        gx0, gy0, gx1, gy1 = self._caixa_goiania
        x0, y0, x1, y1 = (max(caixa[0], gx0), max(caixa[1], gy0), min(caixa[2], gx1), min(caixa[3], gy1))
        candidatos = []
        niveis = sorted(set(nivel_de_desenho(z) for z in range(int(ZOOM_MIN), int(ZOOM_MAX) + 1)))
        aqui = niveis.index(rz) if rz in niveis else 0
        for outro in niveis[aqui + 1:aqui + 2] + niveis[max(0, aqui - 1):aqui]:   # um nível para dentro e um para fora
            if True:
                dzo = z_dados(outro)
                candidatos += [(dzo, tx, ty, outro) for tx, ty in tiles_do_retangulo(x0, y0, x1, y1, dzo)]
        lado = 256.0 * 2 ** (14 - dz)        # um pedaço a mais para cada lado
        for tx, ty in tiles_do_retangulo(max(caixa[0] - lado, gx0), max(caixa[1] - lado, gy0),
                                         min(caixa[2] + lado, gx1), min(caixa[3] + lado, gy1), dz):
            if (dz, tx, ty, rz) not in precisa:
                candidatos.append((dz, tx, ty, rz))
        for chave in reversed(candidatos[:ADIANTAR_POR_VEZ]):   # (o último pedido é o primeiro a ser feito)
            self.fonte.pedir(chave, adiantado=True)

    def _desenhar_fundo(self, chave, preparado):
        """O pedaço no desenho de longe, esticado, onde o detalhado ainda não chegou."""
        g = InstructionGroup()
        for nome, listas in preparado["areas"]:
            if listas:
                g.add(Color(*AREAS[nome]))
                for vertices, indices in listas:
                    g.add(Mesh(vertices=vertices, indices=indices, mode="triangles"))
        for nome, cor_rua, listas in preparado["ruas"]:
            if listas and nome in RUAS:
                g.add(Color(*cor_rua))
                for vertices, indices in listas:
                    g.add(Mesh(vertices=vertices, indices=indices, mode="triangles"))
        self._g_fundo.add(g)
        self._fundo_desenhado[chave] = g

    def _desenhar_tile(self, chave, preparado):
        """Cada camada do tile vira UM subgrupo: tirar o tile depois é tirar
        poucos itens (antes eram centenas de malhas, cada uma procurada na
        lista inteira da camada)."""
        itens = []
        sub = InstructionGroup()
        if chave[3] >= ZOOM_COM_FUNDO:   # chão do pedaço: tapa o desenho esticado que estava no lugar
            lado = 256.0 * 2 ** (14 - chave[0])
            sub.add(Color(*FUNDO))
            sub.add(Rectangle(pos=(chave[1] * lado - self._origem[0], self._origem[1] - (chave[2] + 1) * lado),
                              size=(lado, lado)))
        for nome, listas in preparado["areas"]:
            if listas:
                sub.add(Color(*AREAS[nome]))
                for vertices, indices in listas:
                    sub.add(Mesh(vertices=vertices, indices=indices, mode="triangles"))
        self._g_areas.add(sub)
        itens.append((self._g_areas, sub))
        for nome, cor_rua, listas in preparado["ruas"]:
            if not listas:
                continue
            sub = InstructionGroup()
            sub.add(Color(*cor_rua))
            for vertices, indices in listas:
                sub.add(Mesh(vertices=vertices, indices=indices, mode="triangles"))
            self._g_ruas[nome].add(sub)
            itens.append((self._g_ruas[nome], sub))
        self._desenhados[chave] = itens
        self._t_rotulos = 0.0  # nomes novos disponíveis

    def _apagar_tile(self, chave):
        for grupo, sub in self._desenhados.pop(chave, []):
            grupo.remove(sub)

    def _tile_pronto(self, chave):
        if (chave[0], chave[3]) == self._nivel or (chave[3] == RZ_FUNDO and self._nivel is not None
                                                    and self._nivel[1] >= ZOOM_COM_FUNDO):
            self._tiles_sujo = True
            self._aplicar()

    # --- nomes --------------------------------------------------------------------
    def _textura(self, texto, tamanho, cor, negrito=True, contorno=None):
        """Textura do nome (guardada). None = passou do limite de nomes novos
        desta vez (desenhar texto é caro): fica para a próxima escolha."""
        cor = tuple(cor)
        chave = (texto, tamanho, cor, negrito, contorno)
        tex = self._texturas.get(chave)
        if tex is None:
            # navegando, poucos por vez: desenhar texto é o que mais pesa num
            # quadro, e os lugares da base trazem muitos nomes novos de uma vez
            if self._novas_texturas >= (3 if self._navegando else MAX_TEXTURAS_NOVAS):
                return None
            self._novas_texturas += 1
            rotulo = CoreLabel(text=texto, font_size=tamanho, bold=negrito, color=cor,
                               outline_width=max(1, int(dp(1.6))),
                               outline_color=(contorno or FUNDO)[:3])
            rotulo.refresh()
            tex = rotulo.texture
            self._texturas[chave] = tex
            while len(self._texturas) > MAX_TEXTURAS:
                self._texturas.popitem(last=False)  # a usada há mais tempo
        else:
            self._texturas.move_to_end(chave)
        return tex

    def _pedir_rotulos(self):
        # no voo e com o dedo arrastando/dando zoom, os nomes só acompanham o mapa; a
        # escolha de quais cabem (cara) fica para quando o movimento para
        if self._voo is not None or self._toques:
            return
        if self._ev_rotulos is None:
            espera = max(0.0, REPOSICIONAR_S - (time.time() - self._t_rotulos))
            self._ev_rotulos = Clock.schedule_once(self._escolher_rotulos, espera)

    @seguro
    def _escolher_rotulos(self, *a):
        """Escolhe quais nomes cabem na tela sem se encostar (mais importante
        primeiro; quem já está na tela tem preferência, para os nomes não
        ficarem piscando com o mapa andando/girando)."""
        self._ev_rotulos = None
        self._t_rotulos = time.time()
        self._novas_texturas = 0
        faltou_textura = False
        cx, cy, s, ax, ay, c0, s0 = self._medir_quadro()
        x0, y0, x1, y1 = self.x + dp(8), self.y + dp(8), self.right - dp(8), self.top - dp(8)
        antigos = {id(rot.info): rot for rot in self._rotulos}
        # retângulo (coord. locais) que contém a tela, mesmo girada
        cantos = [self._tela_para_local(px, py) for px, py in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
        lx0, lx1 = min(c[0] for c in cantos), max(c[0] for c in cantos)
        ly0, ly1 = min(c[1] for c in cantos), max(c[1] for c in cantos)
        candidatos = []
        for chave in self._desenhados:
            if (chave[0], chave[3]) != self._nivel:
                continue
            preparado = self.fonte.pronto(chave)
            if not preparado:
                continue
            grade, cel = preparado["grade"], preparado["celula"]
            for gx in range(int(lx0 // cel), int(lx1 // cel) + 1):
                for gy in range(int(ly0 // cel), int(ly1 // cel) + 1):
                    for r in grade.get((gx, gy), ()):  # só os quadrados à vista
                        dx, dy = (r["x"] - cx) * s, (r["y"] - cy) * s
                        sx, sy = ax + dx * c0 - dy * s0, ay + dx * s0 + dy * c0
                        if x0 < sx < x1 and y0 < sy < y1:
                            peso = r["peso"] + (BONUS_JA_NA_TELA if id(r) in antigos else 0.0)
                            candidatos.append((peso, sx, sy, r))
        if self.zoom >= ZOOM_LUGARES:
            conf_min = next(c for z, c in CONF_POR_ZOOM if self.zoom >= z)
            for r in self._lugares_a_vista(lx0, ly0, lx1, ly1):
                if r["conf"] < conf_min:
                    break  # vêm do mais confiável para o menos
                dx, dy = (r["x"] - cx) * s, (r["y"] - cy) * s
                sx, sy = ax + dx * c0 - dy * s0, ay + dx * s0 + dy * c0
                if x0 < sx < x1 and y0 < sy < y1:
                    peso = r["peso"] + (BONUS_JA_NA_TELA if id(r) in antigos else 0.0)
                    candidatos.append((peso, sx, sy, r))
        candidatos.sort(key=lambda t: -t[0])
        cr = self.credito
        ocupados = list(self.areas_cobertas) + [(cr.x, cr.y, cr.right, cr.top)]
        usados_texto, novos = {}, []
        conta = {"rua": 0, "lugar": 0, "poi": 0}
        limite = {"rua": MAX_ROTULOS_RUA, "lugar": MAX_ROTULOS_LUGAR, "poi": MAX_ROTULOS_POI}
        for _, sx, sy, r in candidatos:
            tipo = r["tipo"]
            if conta[tipo] >= limite[tipo]:
                continue
            if tipo == "rua":
                tamanho = sp(13.5) if r["peso"] < 4 else sp(14.5)
                if r["comp"] * s < len(r["texto"]) * tamanho * 0.4:
                    continue  # nem precisa desenhar: o nome não cabe no trecho
                placa = None
                if r["peso"] >= PESO_PLACA:
                    placa = PLACA_CLARO if tema.claro() else PLACA_ESCURO
                    tex = self._textura(r["texto"], tamanho, (1, 1, 1, 1), contorno=placa)
                else:
                    tex = self._textura(r["texto"], tamanho, tema.BRANCO)
                if tex is None:
                    faltou_textura = True
                    continue
                if r["comp"] * s < tex.width * 0.85:
                    continue  # o nome não cabe no trecho
                ang = math.degrees(r["ang"]) + self.rotacao
                ang = (ang + 90.0) % 180.0 - 90.0  # sempre de pé
                ponto = None
            elif tipo == "lugar":
                tex = self._textura(r["texto"], sp(15), tema.LUGAR)
                ang, ponto, placa = 0.0, None, None
            else:
                ponto = CORES_POI.get(r.get("grupo"), CORES_POI["outros"])
                if tema.claro():   # no mapa claro, as cores vivas precisam fechar para aparecer
                    ponto = (ponto[0] * 0.70, ponto[1] * 0.70, ponto[2] * 0.70, 1)
                clara = tema.misturar(ponto, tema.BRANCO, 0.45)   # o nome: a cor puxada para a do texto
                tex = self._textura(r["texto"], sp(12.5), clara, negrito=r.get("grupo") == "praca")
                ang, placa = 0.0, None
            if tex is None:
                faltou_textura = True
                continue
            w, h = tex.size
            c, sn = abs(math.cos(math.radians(ang))), abs(math.sin(math.radians(ang)))
            folga = dp(18) if placa else dp(6)   # (a placa é maior que o texto)
            bw, bh = w * c + h * sn + folga, w * sn + h * c + folga
            cx_ = sx + (w / 2.0 + dp(DIST_NOME_DP) if ponto else 0)
            caixa = (cx_ - bw / 2, sy - bh / 2, cx_ + bw / 2, sy + bh / 2)
            if any(caixa[0] < o[2] and o[0] < caixa[2] and caixa[1] < o[3] and o[1] < caixa[3]
                   for o in ocupados):
                continue
            chave = chave_nome(r["texto"]) if tipo == "poi" else r["texto"]
            visto = usados_texto.get(chave)
            if visto and math.hypot(visto[0] - sx, visto[1] - sy) < dp(260):
                continue
            ocupados.append(caixa)
            usados_texto[chave] = (sx, sy)
            conta[tipo] += 1
            novos.append((r, tex, ponto, placa))
        self._g_rotulos.clear()
        self._rotulos = []
        for r, tex, ponto, placa in novos:
            rot = antigos.get(id(r))
            if rot is None or rot.textura is not tex:
                rot = _Rotulo(r, tex, ponto, placa)
            self._rotulos.append(rot)
            self._g_rotulos.add(rot.grupo)
        self._mover_rotulos()
        self._escolher_sinais()
        if faltou_textura and self._ev_rotulos is None:
            # ainda há nomes para desenhar: continua logo (não espera 0,45 s)
            self._ev_rotulos = Clock.schedule_once(self._escolher_rotulos, 0.05)

    # --- lugares da base da busca -----------------------------------------------------
    def _lugares_a_vista(self, lx0, ly0, lx1, ly1):
        """Rótulos dos lugares da base nos quadrados à vista, do mais
        confiável para o menos. Quadrado ainda não lido: pede numa thread
        (ler o banco aqui daria um tranco) e os nomes entram quando chegar."""
        cantos = [self._local_para_geo(x, y) for x, y in ((lx0, ly0), (lx1, ly0), (lx0, ly1), (lx1, ly1))]
        cel = busca.CELULA_MAPA
        cx0, cx1 = int(math.floor(min(c[0] for c in cantos) / cel)), int(math.floor(max(c[0] for c in cantos) / cel))
        cy0, cy1 = int(math.floor(min(c[1] for c in cantos) / cel)), int(math.floor(max(c[1] for c in cantos) / cel))
        if (cx1 - cx0 + 1) * (cy1 - cy0 + 1) > 9:
            return []  # tela cobrindo área demais (não acontece nos zooms em que isto liga)
        listas = []
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                if (cx, cy) not in self._lugares:
                    self._lugares[(cx, cy)] = None
                    while len(self._lugares) > MAX_CELULAS_LUGARES:
                        self._lugares.popitem(last=False)
                    rede.em_segundo_plano(lambda c=(cx, cy): (c, busca.lugares_da_celula(*c)),
                                          self._lugares_chegaram, lambda e: None)
                elif self._lugares[(cx, cy)]:
                    self._lugares.move_to_end((cx, cy))
                    listas.append(self._lugares[(cx, cy)])
        if len(listas) == 1:
            return listas[0]
        return sorted((r for lista in listas for r in lista), key=lambda r: -r["conf"])

    def _lugares_chegaram(self, resposta):
        celula, linhas = resposta
        if celula not in self._lugares:
            return
        rotulos = []
        for nome, categoria, lat, lon, conf in linhas:
            x, y = self._local(lat, lon)
            legenda = legenda_se_precisa(nome, categoria or "")
            rotulos.append({"texto": "%s · %s" % (nome, legenda) if legenda else nome, "x": x, "y": y,
                            "ang": 0.0, "comp": 0, "peso": 0.25 + conf * 0.2, "tipo": "poi",
                            "grupo": busca.grupo_da_categoria(categoria), "conf": conf})
        self._lugares[celula] = rotulos
        self._t_rotulos = 0.0
        self._pedir_rotulos()

    def _mover_rotulos(self):
        self._mover_sinais()
        for rot in self._rotulos:
            r = rot.info
            sx, sy = self._local_para_tela(r["x"], r["y"])
            rot.mover.xy = (sx, sy)
            if r["tipo"] == "rua":
                ang = math.degrees(r["ang"]) + self.rotacao
                rot.girar.angle = (ang + 90.0) % 180.0 - 90.0

    # --- rota, trilha, destino e seta ---------------------------------------------
    def _refazer_linhas(self, so_trilha=False):
        grupos = [(self._g_trilha, [self._trilha], "trilha")]
        if not so_trilha:
            grupos.append((self._g_rota, [self._rota], "rota"))
            grupos.append((self._g_alt, self._alternativas, "alt"))
        for grupo, listas, tipo in grupos:
            grupo.clear()
            if tipo == "rota":
                self._larg_rota = []      # [(linha, largura em px)] da rota e do que vai junto dela
                if self._revelar is not None:   # a rota ainda está se desenhando: só ela, até a ponta
                    r = self._revelar
                    inicio = [c for p in r["pts"][:1] * 2 for c in p]
                    grupo.add(Color(*tema.com_alfa(tema.CIANO, 0.28)))
                    halo = Line(points=inicio, width=1, joint="round", cap="round", **LINHA_LEVE)
                    grupo.add(halo)
                    grupo.add(Color(*tema.CIANO))
                    linha = Line(points=inicio, width=1, joint="round", cap="round", **LINHA_LEVE)
                    grupo.add(linha)
                    r["linhas"] = (halo, linha)
                    self._larg_rota += [(halo, dp(11)), (linha, dp(4.2))]
                    self._pintar_revelado()
                    continue
                if self._brilho is not None and len(self._rota) >= 2:   # clarão por baixo da rota pronta
                    passo = max(1, len(self._rota) // PONTOS_REVELAR)
                    plano = []
                    for p in self._rota[::passo] + [self._rota[-1]]:
                        plano.extend(self._local(p[0], p[1]))
                    self._cor_brilho = Color(*tema.com_alfa(tema.CIANO, 0.0))
                    grupo.add(self._cor_brilho)
                    clarao = Line(points=plano, width=1, joint="round", cap="round", **LINHA_LEVE)
                    grupo.add(clarao)
                    self._larg_rota.append((clarao, dp(24)))
                if len(self._rota) >= 2:
                    for pontos, magnitude in self._transito:   # por baixo de tudo
                        self._linha(grupo, pontos, "transito%d" % max(1, min(4, magnitude)))
            for pontos in listas:
                if len(pontos) >= 2:
                    self._linha(grupo, pontos, tipo)
            if tipo == "rota" and len(self._rota) >= 2:
                for pontos, nivel in self._trechos:
                    self._linha(grupo, pontos, "pesado" if nivel >= 3 else "movimentado")
        self._larg_usada = None
        self._ajustar_larguras(self._escala_tela())

    def _pintar_revelado(self):
        """A linha da rota até onde a animação já chegou (f de 0 a 1 pelo tempo)."""
        r = self._revelar
        f = min(1.0, max(0.0, (time.monotonic() - r["t0"]) / r["dur"]))
        k = f * f * (3.0 - 2.0 * f)   # sai devagar, corre no meio, chega devagar
        pts, ac = r["pts"], r["ac"]
        alvo = ac[-1] * k
        plano = [pts[0][0], pts[0][1]]
        ponta = pts[0]
        for i in range(1, len(pts)):
            if ac[i] <= alvo:
                plano.extend(pts[i])
                ponta = pts[i]
                continue
            trecho = ac[i] - ac[i - 1]
            t = (alvo - ac[i - 1]) / trecho if trecho > 0 else 0.0
            ponta = (pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * t,
                     pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t)
            plano.extend(ponta)
            break
        if len(plano) < 4:
            plano = plano * 2
        for linha in r["linhas"]:
            linha.points = plano
        r["ponta"] = ponta
        return f >= 1.0

    def _linha(self, grupo, pontos, tipo):
        plano = []
        for p in pontos:
            plano.extend(self._local(p[0], p[1]))
        if tipo == "alt":
            grupo.add(Color(0.05, 0.08, 0.11, 0.9))
            grupo.add(Line(points=plano, width=1, joint="round", cap="round", **LINHA_LEVE))
            grupo.add(Color(0.55, 0.62, 0.70, 0.95))
            grupo.add(Line(points=plano, width=1, joint="round", cap="round", **LINHA_LEVE))
        elif tipo.startswith("transito"):
            grupo.add(Color(*CORES_TRANSITO[int(tipo[-1])]))
            linha = Line(points=plano, width=1, joint="round", cap="round", **LINHA_LEVE)
            grupo.add(linha)
            self._larg_rota.append((linha, dp(14)))
        elif tipo in ("movimentado", "pesado"):
            grupo.add(Color(*(tema.VERMELHO if tipo == "pesado" else tema.LARANJA)))
            linha = Line(points=plano, width=1, joint="round", cap="round", **LINHA_LEVE)
            grupo.add(linha)
            self._larg_rota.append((linha, dp(4.6)))
        elif tipo == "rota":
            # (o brilho em volta da rota usa a 2ª cor do tema: roxa no Monarca, igual à linha nos outros)
            grupo.add(Color(*tema.com_alfa(tema.ROXO, 0.40 if tema.monarca() else 0.28)))
            halo = Line(points=plano, width=1, joint="round", cap="round", **LINHA_LEVE)
            grupo.add(halo)
            grupo.add(Color(*tema.CIANO))
            linha = Line(points=plano, width=1, joint="round", cap="round", **LINHA_LEVE)
            grupo.add(linha)
            self._larg_rota += [(halo, dp(13) if tema.monarca() else dp(11)), (linha, dp(4.2))]
        else:
            grupo.add(Color(*tema.com_alfa(tema.LARANJA, 0.85)))
            grupo.add(Line(points=plano, width=1, joint="round", cap="round", **LINHA_LEVE))

    def _ajustar_larguras(self, s):
        # largura da Line é em unidades locais: compensa a escala para ficar
        # com a mesma espessura na tela
        if self._larg_usada and abs(s / self._larg_usada - 1) < 0.04:
            return
        self._larg_usada = s
        for linha, px in self._larg_rota:   # faixa de trânsito, halo, linha da rota e trechos de avenida
            linha.width = px / s
        for linha in self._larg_geral:      # trânsito da cidade
            linha.width = dp(4.2) / s
        for linha in self._rastro_linhas:   # rastro da seta
            linha.width = dp(3.2) / s
        if self._curva:                     # a ponta da seta da curva é feita no tamanho da tela: refaz
            self._desenhar_seta_curva()
        for linha in (i for i in self._g_trilha.children if isinstance(i, Line)):
            linha.width = dp(2.6) / s
        linhas_alt = [i for i in self._g_alt.children if isinstance(i, Line)]
        for k, linha in enumerate(linhas_alt):  # contorno escuro e miolo cinza
            linha.width = (dp(8) if k % 2 == 0 else dp(4.5)) / s

    def _montar_marcas(self):
        """Destino, círculo de precisão, seta e bolinha: criados uma vez; a
        cada quadro só mudam de lugar (antes eram refeitos 60x/s)."""
        def grupo(*itens):
            g = InstructionGroup()
            for i in itens:
                g.add(i)
            return g
        self._e_dest = [Ellipse(size=(dp(32), dp(32))), Ellipse(size=(dp(18), dp(18))),
                        Ellipse(size=(dp(8), dp(8)))]
        self._m_dest = grupo(Color(*tema.com_alfa(tema.LARANJA, 0.3)), self._e_dest[0],
                             Color(*tema.LARANJA), self._e_dest[1],
                             Color(*tema.FUNDO), self._e_dest[2])
        self._e_prec = Ellipse()
        self._m_prec = grupo(Color(*tema.com_alfa(tema.CIANO, 0.10)), self._e_prec)
        self._e_halo = Ellipse(size=(dp(44), dp(44)))
        self._c_halo = Color(*tema.com_alfa(tema.ROXO, 0.30))   # (a aura em volta da seta)
        self._m_halo = grupo(self._c_halo, self._e_halo)
        # alerta chegando (radar, lombada, semáforo, ocorrência): dois anéis pulsando em volta da placa
        self._pulso = [(Color(1, 1, 1, 0.0), Line(circle=(0, 0, 1), width=dp(2.2))) for _ in range(2)]
        self._m_pulso = grupo(*[i for par in self._pulso for i in par])
        # a onda que sai do ícone tocado
        self._c_onda_toque = Color(1, 1, 1, 0.0)
        self._l_onda_toque = Line(circle=(0, 0, 1), width=dp(2.0))
        self._m_onda_toque = grupo(self._c_onda_toque, self._l_onda_toque)
        self._seta_malha = Mesh(vertices=[0.0] * 16, indices=[0, 1, 2, 3], mode="triangle_fan")
        self._seta_borda = Line(points=[0.0] * 8, close=True, width=dp(1.4))
        self._m_seta = grupo(Color(*tema.BRANCO), self._seta_malha,
                             Color(*tema.CIANO), self._seta_borda)
        self._e_ponto = [Ellipse(size=(dp(18), dp(18))), Ellipse(size=(dp(12), dp(12)))]
        self._m_ponto = grupo(Color(*tema.BRANCO), self._e_ponto[0],
                              Color(*tema.CIANO), self._e_ponto[1])
        # "procurando caminho": 3 ondas saindo de quem pedala e 1 do destino
        self._radar = [(Color(*tema.com_alfa(tema.CIANO, 0.0)), Line(circle=(0, 0, 1), width=dp(1.6)))
                       for _ in range(4)]
        self._m_radar = grupo(*[i for par in self._radar for i in par])
        # a ponta acesa da rota enquanto ela se desenha
        self._e_ponta = [Ellipse(size=(dp(26), dp(26))), Ellipse(size=(dp(11), dp(11)))]
        self._m_ponta = grupo(Color(*tema.com_alfa(tema.CIANO, 0.35)), self._e_ponta[0],
                              Color(*tema.BRANCO), self._e_ponta[1])
        self._tam_dest = [e.size for e in self._e_dest]
        self._visiveis = []
        self._ultima_seta = None

    def _mostrar_marcas(self, quais):
        if quais != self._visiveis:
            self._g_tela.clear()
            for g in quais:
                self._g_tela.add(g)
            self._visiveis = quais

    def _desenhar_tela(self):
        quais = []
        agora = time.monotonic()
        if self._festa is not None:
            t0, onde = self._festa
            if agora - t0 > FESTA_S:
                self._festa = None
            else:
                cx, cy = self._para_tela(*onde)
                some = min(1.0, (FESTA_S - (agora - t0)) / 0.6)   # as últimas ondas vão sumindo
                for n, (cor, anel) in enumerate(self._radar):
                    fase = ((agora - t0) / 1.1 + n / 4.0) % 1.0
                    anel.circle = (cx, cy, dp(14) + fase * dp(120))
                    cor.rgb = tema.VERDE[:3]
                    cor.a = 0.85 * (1.0 - fase) ** 1.4 * some
                quais.append(self._m_radar)
        radar = self._radar_t0 is not None and self._festa is None
        if radar:
            centros = [self._para_tela(*(self._vista or self.eu)[:2])] * 3 if self.eu else [None] * 3
            centros.append(self._para_tela(*self._destino) if self._destino else None)
            for n, ((cor, anel), centro) in enumerate(zip(self._radar, centros)):
                if centro is None:
                    cor.a = 0.0
                    continue
                fase = ((agora - self._radar_t0) / RADAR_VOLTA_S + (n / 3.0 if n < 3 else 0.5)) % 1.0
                alcance = dp(150) if n < 3 else dp(54)
                anel.circle = (centro[0], centro[1], dp(16) + fase * alcance)
                cor.rgb = tema.CIANO[:3]
                cor.a = 0.75 * (1.0 - fase) ** 1.6
            quais.append(self._m_radar)
        if self._destino:
            x, y = self._para_tela(*self._destino)
            cresce, sobe = 1.0, 0.0
            if self._dest_t0 is not None:
                f = (agora - self._dest_t0) / PINO_CAI_S
                if f >= 1.0:
                    self._dest_t0 = None
                else:
                    # cai de cima acelerando, bate no chão e quica duas vezes, cada vez menos
                    # (pedido do dono, 09/10/2026); ao bater, uma onda sai do ponto
                    if f < 0.42:
                        u = f / 0.42
                        sobe, cresce = dp(130) * (1.0 - u * u), 0.55 + 0.45 * u
                    else:
                        if not self._dest_pousou:
                            self._dest_pousou = True
                            self._onda_toque = (agora, self._local(*self._destino), tema.LARANJA[:3])
                        if f < 0.74:
                            u = (f - 0.42) / 0.32
                            sobe = dp(26) * 4.0 * u * (1.0 - u)
                        else:
                            u = (f - 0.74) / 0.26
                            sobe = dp(8) * 4.0 * u * (1.0 - u)
            for e, (w, h) in zip(self._e_dest, self._tam_dest):
                e.size = (w * cresce, h * cresce)
                e.pos = (x - w * cresce / 2.0, y + sobe - h * cresce / 2.0)
            quais.append(self._m_dest)
        if self._revelar is not None:
            x, y = self._local_para_tela(*self._revelar["ponta"])
            for e in self._e_ponta:
                e.pos = (x - e.size[0] / 2.0, y - e.size[1] / 2.0)
            quais.append(self._m_ponta)
        if self.eu:
            precisao = self.eu[3]
            lat, lon, rumo = self._vista or self.eu[:3]
            x, y = self._para_tela(lat, lon)
            if precisao:
                r = precisao / metros_por_px(lat, self.zoom) * self._escala
                if dp(20) < r < max(self.width, self.height):
                    self._e_prec.pos, self._e_prec.size = (x - r, y - r), (2 * r, 2 * r)
                    quais.append(self._m_prec)
            # o halo "respira" devagar (só anda quando o mapa já está animando: não gasta bateria parado)
            respiro = 0.5 + 0.5 * math.sin(agora * 2.0 * math.pi / 2.6)
            raio = dp(21) + dp(5) * respiro
            self._e_halo.size = (2 * raio, 2 * raio)
            self._e_halo.pos = (x - raio, y - raio)
            self._c_halo.a = 0.34 - 0.14 * respiro
            quais.append(self._m_halo)
            if rumo is None:
                for e in self._e_ponto:
                    e.pos = (x - e.size[0] / 2.0, y - e.size[1] / 2.0)
                quais.append(self._m_ponto)
            else:
                # seta: ângulo na tela = rumo - rotação do mapa (horário a partir de cima)
                ang = -(rumo - self.rotacao)
                if self._ultima_seta != (x, y, ang):
                    self._ultima_seta = (x, y, ang)
                    pts = []
                    for px, py in ((0, dp(19)), (dp(13), -dp(13)), (0, -dp(5)), (-dp(13), -dp(13))):
                        rx, ry = _girar(px, py, ang)
                        pts.append((x + rx, y + ry))
                    self._seta_malha.vertices = [v for px, py in pts for v in (px, py, 0, 0)]
                    self._seta_borda.points = [c for p in pts for c in p]
                quais.append(self._m_seta)
        if self._onda_toque is not None:
            f = (agora - self._onda_toque[0]) / 0.42
            if f >= 1.0:
                self._onda_toque = None
            else:
                ox, oy = self._local_para_tela(*self._onda_toque[1])
                self._l_onda_toque.circle = (ox, oy, dp(12) + f * dp(30))
                self._c_onda_toque.rgb = self._onda_toque[2] if len(self._onda_toque) > 2 else tema.ROXO[:3]
                self._c_onda_toque.a = 0.85 * (1.0 - f) ** 1.3
                quais.append(self._m_onda_toque)
        if self._destaque is not None:
            (dlat, dlon), cor = self._destaque
            px, py = self._para_tela(dlat, dlon)
            for n, (c, anel) in enumerate(self._pulso):
                fase = (agora / 1.1 + n * 0.5) % 1.0
                anel.circle = (px, py, dp(20) + fase * dp(34))
                c.rgb = cor
                c.a = 0.9 * (1.0 - fase) ** 1.5
            quais.append(self._m_pulso)
        self._mostrar_marcas(quais)

    # --- animação (seta andando, câmera seguindo, zoom suave, inércia) ---------------
    def _ligar_animacao(self):
        if self._ev_anim is None and self.ativo:
            # a cada quadro (0), não 1/60: sem quadro pulado nem repetido
            self._ev_anim = Clock.schedule_interval(self._passo_animacao, 0)

    def _parar_animacao(self):
        if self._ev_anim is not None:
            self._ev_anim.cancel()
            self._ev_anim = None
        self._velocidade = (0.0, 0.0)

    def _guardar_rastro(self, vista):
        """O rastro curto atrás da seta: um ponto a cada RASTRO_PASSO_M, em três
        pedaços cada vez mais apagados para trás."""
        ponto = self._local(vista[0], vista[1])
        passo = RASTRO_PASSO_M / max(0.05, metros_por_px(vista[0], 14))   # em unidades locais
        if self._rastro:
            ux, uy = self._rastro[-1]
            d = math.hypot(ponto[0] - ux, ponto[1] - uy)
            if d < passo:
                return
            if d > passo * 12:   # pulou (GPS voltou, rota nova): o rastro velho não liga com o novo
                self._rastro.clear()
        self._rastro.append(ponto)
        pts = list(self._rastro)
        terco = max(1, len(pts) // 3)
        pedacos = (pts[:terco + 1], pts[terco:2 * terco + 1], pts[2 * terco:])
        for linha, pedaco in zip(self._rastro_linhas, pedacos):
            if len(pedaco) < 2:
                pedaco = [pts[0], pts[0]]
            linha.points = [c for p in pedaco for c in p]

    def _posicao_prevista(self, agora):
        """(lat, lon, rumo, andando) de onde a seta deve estar agora."""
        lat, lon, rumo, vel, t = self._fix
        idade = min(max(0.0, agora - t), MAX_PREVER_S)
        andando = vel > 0.5 and agora - t < MAX_PREVER_S
        if self.prever is not None:
            p = self.prever(idade)  # navegando: anda em cima da rota
            if p is not None:
                return p[0], p[1], p[2], andando
        if not andando or rumo is None:
            return lat, lon, rumo, False
        d = vel * idade
        a = math.radians(rumo)
        return (lat + d * math.cos(a) / 111320.0,
                lon + d * math.sin(a) / (111320.0 * math.cos(math.radians(lat))), rumo, True)

    def _passo_animacao(self, dt):
        try:
            return self._passo_animacao_seguro(dt)
        except Exception as e:  # a animação não pode morrer presa (_ev_anim nunca mais religaria)
            import diagnostico
            diagnostico.registrar_contornado(type(e), e, e.__traceback__, "erro na animação do mapa")
            self._ev_anim = None
            self._em_lote = False
            return False

    def _passo_animacao_seguro(self, dt):
        if not self.ativo:
            self._ev_anim = None
            return False
        dt = min(dt, 0.1)
        tela_animando()  # a thread do mapa dá a vez para a tela
        mexeu = False
        refazer = False
        agora = time.monotonic()
        if self._radar_t0 is not None:
            if agora - self._radar_t0 > RADAR_MAX_S:
                self._radar_t0 = None
            mexeu = True
        if (self._dest_t0 is not None or self._festa is not None or self._destaque is not None
                or self._onda_toque is not None or self._salto is not None):
            mexeu = True
        if self._revelar is not None:
            mexeu = True
            if self._pintar_revelado():   # chegou ao destino: rota inteira + clarão
                self._revelar = None
                self._brilho = agora
                refazer = True
        elif self._brilho is not None:
            f = (agora - self._brilho) / BRILHO_S
            mexeu = True
            if f >= 1.0:
                self._brilho = None
                refazer = True
            else:
                self._cor_brilho.a = 0.55 * (1.0 - f) ** 2
        if refazer:
            self._refazer_linhas()
        self._em_lote = True
        try:
            if self._voo is not None:
                v = self._voo
                f = min(1.0, (agora - v["t0"]) / v["dur"])
                k = f * f * (3.0 - 2.0 * f)
                (x0, y0), z0, a0, r0 = v["de"]
                (x1, y1), z1, a1 = v["para"]
                dz = z1 - z0
                # o chão anda na mesma velocidade NA TELA do começo ao fim, mesmo
                # com o zoom mudando (senão dispara no começo ou no fim do voo)
                kp = k if abs(dz) < 0.01 else (1.0 - 2.0 ** (-dz * k)) / (1.0 - 2.0 ** (-dz))
                if f >= 1.0:
                    self.centro, self.ancora = v["centro"], a1
                    self.zoom, self.rotacao = z1, v["giro"]
                    self._voo = None
                    self._rz_fixo = None
                    self._t_rotulos = 0.0   # chegou: agora escolhe os nomes da vista nova
                else:
                    self.centro = self._local_para_geo(x0 + (x1 - x0) * kp, y0 + (y1 - y0) * kp)
                    self.ancora = (a0[0] + (a1[0] - a0[0]) * k, a0[1] + (a1[1] - a0[1]) * k)
                    self.zoom = z0 + dz * k
                    self.rotacao = (r0 + _dif_angulo(r0, v["giro"]) * k) % 360.0
                mexeu = True
            if self._fix is not None:
                lat, lon, rumo, andando = self._posicao_prevista(time.monotonic())
                v = self._vista
                if v is None or abs(lat - v[0]) + abs(lon - v[1]) > 0.003:  # ~300 m: pula
                    nova = (lat, lon, rumo)
                else:
                    k = 1.0 - math.exp(-dt * SUAVE_POS)
                    r = v[2]
                    if rumo is not None:
                        r = rumo if r is None else (r + _dif_angulo(r, rumo) * k) % 360.0
                    nova = (v[0] + (lat - v[0]) * k, v[1] + (lon - v[1]) * k, r)
                parado = (abs(nova[0] - lat) < 1e-7 and abs(nova[1] - lon) < 1e-7
                          and (rumo is None or abs(_dif_angulo(nova[2], rumo)) < 0.2))
                self._vista = nova
                mexeu = mexeu or andando or not parado
                self._guardar_rastro(nova)
            if self.seguindo and self._vista is not None and self._voo is None:
                lat, lon, rumo = self._vista
                clat, clon = self.centro
                if abs(lat - clat) < 1e-7 and abs(lon - clon) < 1e-7:
                    self.centro = (lat, lon)
                else:
                    k = 1.0 - math.exp(-dt * SUAVE_CAMERA)
                    self.centro = (clat + (lat - clat) * k, clon + (lon - clon) * k)
                    mexeu = True
                girando = self._navegando and self.girar
                if girando and rumo is not None:
                    alvo_rot = rumo
                else:
                    alvo_rot = self.rotacao if girando else 0.0
                d_rot = _dif_angulo(self.rotacao, alvo_rot)
                if abs(d_rot) > 0.1:
                    self.rotacao = (self.rotacao + d_rot * (1.0 - math.exp(-dt * SUAVE_GIRO))) % 360.0
                    mexeu = True
                elif d_rot:
                    self.rotacao = alvo_rot % 360.0
            vx, vy = self._velocidade
            if not self.seguindo and math.hypot(vx, vy) > dp(8):
                self._arrastar(vx * dt, vy * dt)
                queda = math.exp(-dt * INERCIA)
                self._velocidade = (vx * queda, vy * queda)
                mexeu = True
            else:
                self._velocidade = (0.0, 0.0)
            if self._zoom_toque is not None:
                zt = self._zoom_toque
                f = min(1.0, (agora - zt["t0"]) / ZOOM_TOQUE_S)
                self._zoom_no_ponto(zt["z0"] + (zt["z1"] - zt["z0"]) * (1.0 - (1.0 - f) ** 3), *zt["onde"])
                self._em_lote = True   # (_zoom_no_ponto solta o lote; o _aplicar é um só, no fim)
                if f >= 1.0:
                    self._zoom_toque = None
                    self._t_rotulos = 0.0   # chegou: os nomes da vista nova
                mexeu = True
            elif self._alvo_zoom is not None and self._voo is None:
                dz = self._alvo_zoom - self.zoom
                if abs(dz) < 0.005:
                    self.zoom = self._alvo_zoom
                    if not self._navegando:
                        self._alvo_zoom = None
                else:
                    self.zoom += dz * (1.0 - math.exp(-dt * 8.0))
                    mexeu = True
        finally:
            self._em_lote = False
        self._aplicar()
        if not mexeu:
            self._ev_anim = None
            return False

    # --- toque: arrastar, pinça, duplo toque, rodinha do mouse -----------------
    def _arrastar(self, dx, dy):
        s = self._escala_tela()
        gx, gy = _girar(dx, dy, -self.rotacao)
        cx, cy = self._local(*self.centro)
        self.centro = goiania.prender(*self._local_para_geo(cx - gx / s, cy - gy / s))

    def _zoom_no_ponto(self, novo_zoom, sx, sy):
        """Muda o zoom mantendo parado o ponto da tela (sx, sy) (sob os dedos)."""
        antes = self._tela_para_local(sx, sy)
        self._em_lote = True  # quem chamou faz o _aplicar (uma vez só)
        try:
            self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, novo_zoom))
        finally:
            self._em_lote = False
        depois = self._tela_para_local(sx, sy)
        cx, cy = self._local(*self.centro)
        self.centro = goiania.prender(*self._local_para_geo(cx + antes[0] - depois[0],
                                                             cy + antes[1] - depois[1]))

    def _sair_do_seguir(self):
        self._cancelar_voo()
        self._zoom_toque = None
        if self.seguindo:
            self.seguindo = False
        if not self._navegando:
            self._alvo_zoom = None

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        if super().on_touch_down(touch):
            return True
        self._t_mexeu = time.time()
        self._cancelar_voo()   # pôs o dedo: o mapa é dele
        if getattr(touch, "is_mouse_scrolling", False):
            self._alvo_zoom = None
            self._zoom_no_ponto(self.zoom + (0.5 if touch.button == "scrolldown" else -0.5), *touch.pos)
            self._aplicar()
            return True
        self._velocidade = (0.0, 0.0)
        if touch.is_double_tap:
            # dois toques: aproxima um nível NAQUELE ponto, deslizando (antes pulava de uma
            # vez só), e uma onda marca onde foi (pedido do dono, 09/10/2026)
            self._alvo_zoom = None
            de = self._zoom_toque["z1"] if self._zoom_toque else self.zoom   # (toques seguidos somam)
            self._zoom_toque = {"t0": time.monotonic(), "z0": self.zoom,
                                "z1": max(ZOOM_MIN, min(ZOOM_MAX, de + 1.0)), "onde": tuple(touch.pos)}
            self._onda_toque = (time.monotonic(), self._tela_para_local(*touch.pos), tema.CIANO[:3])
            self._ligar_animacao()
            return True
        touch.grab(self)
        self._toques.append(touch)
        touch.ud["mapa_inicio"] = touch.pos
        self._movs = []
        self._cancelar_segurar()
        if len(self._toques) == 1 and self.ao_segurar is not None:
            self._ev_segurar = Clock.schedule_once(lambda dt: self._segurou(touch), SEGURAR_S)
        return True

    def _cancelar_segurar(self):
        if self._ev_segurar is not None:
            self._ev_segurar.cancel()
            self._ev_segurar = None

    def _segurou(self, touch):
        self._ev_segurar = None
        if touch in self._toques and len(self._toques) == 1 and self.ao_segurar is not None:
            lat, lon = self._local_para_geo(*self._tela_para_local(*touch.pos))
            self.ao_segurar(lat, lon)

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        self._t_mexeu = time.time()
        tela_animando()
        x0, y0 = touch.ud.get("mapa_inicio", touch.pos)
        if len(self._toques) >= 2 or math.hypot(touch.x - x0, touch.y - y0) > dp(10):
            self._cancelar_segurar()  # mexeu: é arrasto/pinça, não "segurar"
        if len(self._toques) >= 2:
            a, b = self._toques[0], self._toques[1]
            outro = b if touch is a else a
            antes = math.hypot(touch.px - outro.x, touch.py - outro.y)
            agora = math.hypot(touch.x - outro.x, touch.y - outro.y)
            if antes > dp(10) and agora > dp(10):
                self._alvo_zoom = self._zoom_toque = None
                meio = ((touch.x + outro.x) / 2.0, (touch.y + outro.y) / 2.0)
                self._zoom_no_ponto(self.zoom + math.log2(agora / antes), *meio)
                self._aplicar()
            return True
        x0, y0 = touch.ud.get("mapa_inicio", touch.pos)
        if self.seguindo and math.hypot(touch.x - x0, touch.y - y0) < dp(8):
            return True  # tremidinha do dedo não tira do modo seguir
        self._sair_do_seguir()
        self._arrastar(touch.dx, touch.dy)
        self._movs.append((time.time(), touch.dx, touch.dy))
        self._movs = self._movs[-6:]
        self._aplicar()
        return True

    def _depois_do_toque(self, abrir):
        if ATRASO_TOQUE_S > 0:
            Clock.schedule_once(lambda dt: abrir(), ATRASO_TOQUE_S)
        else:
            abrir()

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        self._t_mexeu = time.time()
        self._cancelar_segurar()
        if touch in self._toques:
            self._toques.remove(touch)
        # toque curto e parado em cima de um ícone do trânsito: abre o que é
        inicio = touch.ud.get("mapa_inicio")
        if (self.ao_tocar_ocorrencia is not None and self._ocorr_na_tela and not self._toques and inicio
                and math.hypot(touch.x - inicio[0], touch.y - inicio[1]) < dp(12)
                and time.time() - touch.time_start < 0.5):
            perto = None
            for lx, ly, o in self._ocorr_na_tela:
                sx, sy = self._local_para_tela(lx, ly)
                d = math.hypot(touch.x - sx, touch.y - sy)
                if d < dp(TOQUE_OCORRENCIA_DP) and (perto is None or d < perto[0]):
                    perto = (d, o)
            if perto is not None:
                self._movs = []
                ocorrencia = perto[1]
                self.saltar_icone(ocorrencia["pontos"][len(ocorrencia["pontos"]) // 2])
                self._depois_do_toque(lambda: self.ao_tocar_ocorrencia(ocorrencia))
                return True
        # ... ou em cima de um lugar (o emblema ou o nome): abre o cartão dele
        if (self.ao_tocar_lugar is not None and not self._toques and inicio
                and math.hypot(touch.x - inicio[0], touch.y - inicio[1]) < dp(12)
                and time.time() - touch.time_start < 0.5):
            lugar = self.lugar_em(touch.x, touch.y)
            if lugar is not None:
                self._movs = []
                rot = lugar.pop("_rot", None)
                if rot is not None:   # o emblema dá um pulo e uma onda sai dele
                    Animation.cancel_all(rot.cresce)
                    (Animation(x=1.45, y=1.45, d=0.10, t="out_quad")
                     + Animation(x=1.0, y=1.0, d=0.22, t="out_back")).start(rot.cresce)
                    self._onda_toque = (time.monotonic(), (rot.info["x"], rot.info["y"]))
                    self._ligar_animacao()
                self._depois_do_toque(lambda: self.ao_tocar_lugar(lugar))
                return True
        # inércia: continua deslizando na velocidade dos últimos movimentos
        agora = time.time()
        recentes = [m for m in self._movs if agora - m[0] < 0.12]
        if not self._toques and len(recentes) >= 2 and not self.seguindo:
            dur = max(agora - recentes[0][0], 1 / 60.0)
            self._velocidade = (sum(m[1] for m in recentes) / dur, sum(m[2] for m in recentes) / dur)
            self._ligar_animacao()
        self._movs = []
        if not self._toques:
            self._pedir_rotulos()   # soltou o dedo: os nomes da vista nova entram
        return True
