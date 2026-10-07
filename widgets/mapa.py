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
from kivy.graphics import (Color, Ellipse, InstructionGroup, Line, Mesh, PopMatrix,
                           PushMatrix, Rectangle, Rotate, RoundedRectangle, Scale, Translate)
from kivy.metrics import Metrics, dp, sp
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import busca
import goiania
import rede
import sinais
import tema
from diagnostico import seguro
from mapa_vetor import (AREAS, FUNDO, RUAS, SETAS, FonteVetorial, chave_nome, legenda_se_precisa,
                        tela_animando, tiles_do_retangulo, z_dados)

ZOOM_MIN, ZOOM_MAX = 11.0, 19.0   # o app é só de Goiânia: de longe, a cidade inteira
SEGURAR_S = 0.6                  # dedo parado esse tempo = marcar o ponto
TAM = 256.0
MAX_ROTULOS_RUA = 30
MAX_ROTULOS_LUGAR = 8
MAX_ROTULOS_POI = 14
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
MAX_TEXTURAS_NOVAS = 8     # por escolha de nomes, no máximo tantos nomes novos desenhados
# Lugares da base da busca (69.900 em Goiânia) desenhados no mapa: o mapa do
# OpenStreetMap tem pouco comércio cadastrado na cidade. Só de perto, e
# quanto mais perto, mais lugares (pela "confiança" da base).
ZOOM_LUGARES = 16.5
CONF_POR_ZOOM = ((18.3, 0.75), (17.5, 0.86), (16.5, 0.94))   # (zoom mínimo, confiança mínima)
MAX_CELULAS_LUGARES = 24
# (16 enchia a tela de semáforos no centro da cidade, andando livre)
ZOOM_RADARES = 14.5        # radares aparecem bem antes
ZOOM_SINAIS = 17.0         # fora da navegação, semáforos e lombadas a partir desse zoom
MAX_SINAIS = 40


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
    """Um nome desenhado na tela (posição/ângulo atualizados a cada quadro)."""

    def __init__(self, info, textura, ponto=None):
        self.info = info
        self.textura = textura
        self.grupo = InstructionGroup()
        if ponto is not None:
            self.grupo.add(Color(*FUNDO))   # aro escuro: a bolinha aparece em cima de qualquer cor
            self.aro = Ellipse(size=(dp(15), dp(15)))
            self.grupo.add(self.aro)
            self.grupo.add(Color(*ponto))
            self.bolinha = Ellipse(size=(dp(11), dp(11)))
            self.grupo.add(self.bolinha)
        else:
            self.bolinha = None
        self.grupo.add(Color(1, 1, 1, 1))
        self.grupo.add(PushMatrix())
        self.mover = Translate(0, 0)
        self.girar = Rotate(angle=0, axis=(0, 0, 1))
        self.grupo.add(self.mover)
        self.grupo.add(self.girar)
        w, h = textura.size
        deslocar = dp(11) if ponto is not None else -w / 2.0
        self.grupo.add(Rectangle(texture=textura, size=(w, h), pos=(deslocar, -h / 2.0)))
        self.grupo.add(PopMatrix())


class MapaHUD(Widget):
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
        self._origem = mundo(self.centro[0], self.centro[1], 14)
        self._rota, self._trilha, self._destino = [], [], None
        self._trechos = []                  # avenidas da rota: [(pontos, nível)]
        self._alternativas = []
        self._desenhados = {}               # (dz, tx, ty, rz) -> [(grupo, instrução), ...]
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
        self.ao_segurar = None              # ao_segurar(lat, lon): dedo parado no mapa
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
        self._g_areas = InstructionGroup()
        self.canvas.add(self._g_areas)
        self._g_ruas = {}
        for nome in RUAS:  # da menos importante para a mais (a mais fica por cima)
            self._g_ruas[nome] = InstructionGroup()
            self.canvas.add(self._g_ruas[nome])
        for nome in SETAS:  # setas de mão única: por cima de todas as ruas, por baixo da rota
            self._g_ruas[nome] = InstructionGroup()
            self.canvas.add(self._g_ruas[nome])
        self._g_trilha = InstructionGroup()
        self._g_alt = InstructionGroup()      # outras rotas que dá para escolher (cinza)
        self._g_rota = InstructionGroup()
        self.canvas.add(self._g_trilha)
        self.canvas.add(self._g_alt)
        self.canvas.add(self._g_rota)
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
        self._navegando = ligado
        # navegando e girando: a seta fica mais embaixo, sobra mapa à frente
        self.ancora = self.ancora_nav if (ligado and self.girar) else (0.5, 0.5)
        if ligado:
            self.seguindo = True
            self._alvo_zoom = ZOOM_NAV_PERTO
        else:
            self._alvo_zoom = None
            self.prever = None
        self._aplicar()
        self._ligar_animacao()

    def definir_rota(self, pontos):
        self._rota = list(pontos)
        self._trechos = []          # as avenidas eram da rota antiga
        self._refazer_linhas()

    def definir_trechos(self, trechos):
        """Trechos da rota em via movimentada [(pontos, nível)]: desenhados por
        cima da linha em laranja (movimentado) ou vermelho (pesado), para a
        pessoa ver ONDE o caminho pede mais atenção."""
        self._trechos = [(list(pontos), nivel) for pontos, nivel in trechos if len(pontos) >= 2]
        self._refazer_linhas()

    def definir_alternativas(self, listas):
        """Rotas que a pessoa pode escolher em vez da atual (desenho cinza)."""
        self._alternativas = [list(p) for p in listas]
        self._refazer_linhas()

    def definir_trilha(self, pontos):
        self._trilha = list(pontos)
        self._refazer_linhas(so_trilha=True)

    def definir_destino(self, lat_lon):
        self._destino = lat_lon
        self._desenhar_tela()

    def enquadrar(self, pontos, margem_px=None, cobertos=(0, 0, 0, 0)):
        """Mostra todos os pontos (norte para cima), sem seguir quem pedala.
        `cobertos` = (esquerda, baixo, direita, cima) em px tapados por
        painéis: a rota cabe no pedaço de mapa que sobra visível."""
        if not pontos:
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
        self.ancora = ((esq + livre_w / 2.0) / max(self.width, 1),
                       (baixo + livre_h / 2.0) / max(self.height, 1))
        self._parar_animacao()
        self.centro = meio
        self.rotacao = 0.0
        self.zoom = max(ZOOM_MIN, min(17.0, z))
        self._aplicar()

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
        if self._rz is None or abs(self.zoom - self._rz) > HISTERESE_ZOOM:
            self._rz = int(max(ZOOM_MIN, min(ZOOM_MAX, round(self.zoom))))
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
        for chave in sorted(precisa, key=lambda c: (c[1] + 0.5 - mx) ** 2 + (c[2] + 0.5 - my) ** 2):
            if chave in self._desenhados:
                continue
            preparado = self.fonte.pronto(chave)
            if preparado is None:
                self.fonte.pedir(chave)
                faltando = True
            elif time.perf_counter() - t0 > ORCAMENTO_TILES_S:
                faltando = adiado = True  # monta no próximo quadro (sem tranco)
            else:
                self._desenhar_tile(chave, preparado)
        if adiado:
            self._tiles_sujo = True
            Clock.schedule_once(lambda dt: self._aplicar(), 0)
        for chave in list(self._desenhados):
            mesmo_nivel = (chave[0], chave[3]) == nivel
            # desenho de outro zoom só sai quando o novo já cobriu a tela
            if (mesmo_nivel and chave not in precisa) or (not mesmo_nivel and not faltando):
                self._apagar_tile(chave)
        if nivel != self._nivel:
            self._nivel = nivel
            self._t_rotulos = 0.0

    def _desenhar_tile(self, chave, preparado):
        """Cada camada do tile vira UM subgrupo: tirar o tile depois é tirar
        poucos itens (antes eram centenas de malhas, cada uma procurada na
        lista inteira da camada)."""
        itens = []
        sub = InstructionGroup()
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
        if (chave[0], chave[3]) == self._nivel:
            self._tiles_sujo = True
            self._aplicar()

    # --- nomes --------------------------------------------------------------------
    def _textura(self, texto, tamanho, cor, negrito=True):
        """Textura do nome (guardada). None = passou do limite de nomes novos
        desta vez (desenhar texto é caro): fica para a próxima escolha."""
        cor = tuple(cor)
        chave = (texto, tamanho, cor, negrito)
        tex = self._texturas.get(chave)
        if tex is None:
            # navegando, poucos por vez: desenhar texto é o que mais pesa num
            # quadro, e os lugares da base trazem muitos nomes novos de uma vez
            if self._novas_texturas >= (3 if self._navegando else MAX_TEXTURAS_NOVAS):
                return None
            self._novas_texturas += 1
            rotulo = CoreLabel(text=texto, font_size=tamanho, bold=negrito, color=cor,
                               outline_width=max(1, int(dp(1.6))), outline_color=FUNDO[:3])
            rotulo.refresh()
            tex = rotulo.texture
            self._texturas[chave] = tex
            while len(self._texturas) > MAX_TEXTURAS:
                self._texturas.popitem(last=False)  # a usada há mais tempo
        else:
            self._texturas.move_to_end(chave)
        return tex

    def _pedir_rotulos(self):
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
                ang, ponto = 0.0, None
            else:
                ponto = CORES_POI.get(r.get("grupo"), CORES_POI["outros"])
                if tema.claro():   # no mapa claro, as cores vivas precisam fechar para aparecer
                    ponto = (ponto[0] * 0.70, ponto[1] * 0.70, ponto[2] * 0.70, 1)
                clara = tema.misturar(ponto, tema.BRANCO, 0.45)   # o nome: a cor puxada para a do texto
                tex = self._textura(r["texto"], sp(12.5), clara, negrito=r.get("grupo") == "praca")
                ang = 0.0
            if tex is None:
                faltou_textura = True
                continue
            w, h = tex.size
            c, sn = abs(math.cos(math.radians(ang))), abs(math.sin(math.radians(ang)))
            bw, bh = w * c + h * sn + dp(6), w * sn + h * c + dp(6)
            cx_ = sx + (w / 2.0 + dp(11) if ponto else 0)
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
            novos.append((r, tex, ponto))
        self._g_rotulos.clear()
        self._rotulos = []
        for r, tex, ponto in novos:
            rot = antigos.get(id(r))
            if rot is None or rot.textura is not tex:
                rot = _Rotulo(r, tex, ponto)
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

    # --- semáforos e lombadas -------------------------------------------------------
    @staticmethod
    def _icone(tipo):
        g, tr = InstructionGroup(), Translate(0, 0)
        g.add(PushMatrix())
        g.add(tr)
        if tipo in ("casa", "trabalho"):
            # pino do atalho (como o da casa no Waze): gota na cor do app com o desenho dentro
            cor, fundo = tema.CIANO, tema.FUNDO
            g.add(Color(*tema.com_alfa(fundo, 0.9)))
            g.add(Ellipse(pos=(-dp(17), -dp(3)), size=(dp(34), dp(34))))
            g.add(Color(*cor))
            g.add(Ellipse(pos=(-dp(14.5), -dp(0.5)), size=(dp(29), dp(29))))
            g.add(Mesh(vertices=[-dp(7), dp(3), 0, 0, dp(7), dp(3), 0, 0, 0, -dp(9), 0, 0],
                       indices=[0, 1, 2], mode="triangles"))                 # a ponta da gota
            g.add(Color(*fundo))
            if tipo == "casa":
                g.add(Mesh(vertices=[-dp(8), dp(14), 0, 0, dp(8), dp(14), 0, 0, 0, dp(22), 0, 0],
                           indices=[0, 1, 2], mode="triangles"))             # telhado
                g.add(Rectangle(pos=(-dp(5.5), dp(6)), size=(dp(11), dp(8.5))))
            else:
                g.add(Rectangle(pos=(-dp(8), dp(7)), size=(dp(16), dp(11))))  # maleta
                g.add(Line(points=[-dp(3.5), dp(18), -dp(3.5), dp(21.5), dp(3.5), dp(21.5), dp(3.5), dp(18)],
                           width=dp(1.3)))
        elif sinais.e_radar(tipo):
            # placa de limite: disco branco, aro vermelho e o número (ou "R" sem limite informado)
            g.add(Color(0.85, 0.10, 0.16, 1))
            g.add(Ellipse(pos=(-dp(13), -dp(13)), size=(dp(26), dp(26))))
            g.add(Color(1, 1, 1, 1))
            g.add(Ellipse(pos=(-dp(9.5), -dp(9.5)), size=(dp(19), dp(19))))
            limite = sinais.limite_do_radar(tipo)
            rotulo = CoreLabel(text=str(limite) if limite else "R", font_size=sp(11), bold=True,
                               color=(0.05, 0.07, 0.10, 1))
            rotulo.refresh()
            tw, th = rotulo.texture.size
            g.add(Color(1, 1, 1, 1))
            g.add(Rectangle(texture=rotulo.texture, size=(tw, th), pos=(-tw / 2.0, -th / 2.0)))
        elif tipo == "semaforo":  # caixinha escura com as três luzes
            g.add(Color(0.02, 0.03, 0.05, 0.95))
            g.add(RoundedRectangle(pos=(-dp(5), -dp(11)), size=(dp(10), dp(22)), radius=[dp(3)]))
            for k, cor in enumerate(((0.95, 0.25, 0.25, 1), (1.0, 0.78, 0.2, 1), (0.25, 0.9, 0.45, 1))):
                g.add(Color(*cor))
                g.add(Ellipse(pos=(-dp(3), dp(4) - k * dp(7)), size=(dp(6), dp(6))))
        else:  # lombada: triângulo laranja de aviso
            pts = [(0, dp(10)), (dp(10), -dp(8)), (-dp(10), -dp(8))]
            g.add(Color(*tema.LARANJA))
            g.add(Mesh(vertices=[v for x, y in pts for v in (x, y, 0, 0)], indices=[0, 1, 2],
                       mode="triangles"))
            g.add(Color(*tema.FUNDO))
            g.add(Line(points=[c for p in pts for c in p], close=True, width=dp(1.3)))
            g.add(Rectangle(pos=(-dp(1.2), -dp(3)), size=(dp(2.4), dp(7))))
        g.add(PopMatrix())
        return g, tr

    def _escolher_sinais(self):
        """Ícones dos semáforos/lombadas à vista (de perto: de longe poluiria)."""
        self._g_sinais.clear()
        self._sinais = []
        if self.sinais_rota is None and self.zoom < ZOOM_RADARES and not self.marcos:
            return
        cantos = [self._local_para_geo(*self._tela_para_local(px, py))
                  for px, py in ((self.x, self.y), (self.right, self.y), (self.x, self.top),
                                 (self.right, self.top))]
        lats, lons = [c[0] for c in cantos], [c[1] for c in cantos]
        if len(self._icones) > 400:
            self._icones.clear()
        postos = []
        la0, la1, lo0, lo1 = min(lats), max(lats), min(lons), max(lons)
        if self.sinais_rota is not None:
            fonte = [p for p in self.sinais_rota if la0 <= p[0] <= la1 and lo0 <= p[1] <= lo1]
        elif self.zoom < ZOOM_RADARES:
            fonte = []
        else:
            # de mais longe só os radares (são poucos e importam); semáforo e lombada, de perto
            fonte = sinais.na_caixa(min(lats), min(lons), max(lats), max(lons), 300,
                                    so_radares=self.zoom < ZOOM_SINAIS)
        # Casa e Trabalho: sempre à vista (são referência), por cima dos outros
        fonte = list(fonte) + [p for p in self.marcos if la0 <= p[0] <= la1 and lo0 <= p[1] <= lo1]
        for lat, lon, tipo in fonte:
            if len(postos) >= MAX_SINAIS:
                break
            sx, sy = self._para_tela(lat, lon)
            # cruzamento com vários semáforos mapeados: um ícone só
            if any(t == tipo and abs(sx - x) < dp(30) and abs(sy - y) < dp(30) for x, y, t in postos):
                continue
            postos.append((sx, sy, tipo))
            item = self._icones.get((lat, lon, tipo))
            if item is None:
                item = self._icones[(lat, lon, tipo)] = self._icone(tipo)
            self._g_sinais.add(item[0])
            lx, ly = self._local(lat, lon)
            self._sinais.append((lx, ly, item[1]))
        self._mover_sinais()

    def _mover_sinais(self):
        for lx, ly, tr in self._sinais:
            tr.xy = self._local_para_tela(lx, ly)

    def _mover_rotulos(self):
        self._mover_sinais()
        for rot in self._rotulos:
            r = rot.info
            sx, sy = self._local_para_tela(r["x"], r["y"])
            rot.mover.xy = (sx, sy)
            if r["tipo"] == "rua":
                ang = math.degrees(r["ang"]) + self.rotacao
                rot.girar.angle = (ang + 90.0) % 180.0 - 90.0
            if rot.bolinha is not None:
                rot.bolinha.pos = (sx - dp(5.5), sy - dp(5.5))
                rot.aro.pos = (sx - dp(7.5), sy - dp(7.5))

    # --- rota, trilha, destino e seta ---------------------------------------------
    def _refazer_linhas(self, so_trilha=False):
        grupos = [(self._g_trilha, [self._trilha], "trilha")]
        if not so_trilha:
            grupos.append((self._g_rota, [self._rota], "rota"))
            grupos.append((self._g_alt, self._alternativas, "alt"))
        for grupo, listas, tipo in grupos:
            grupo.clear()
            for pontos in listas:
                if len(pontos) >= 2:
                    self._linha(grupo, pontos, tipo)
            if tipo == "rota" and len(self._rota) >= 2:
                for pontos, nivel in self._trechos:
                    self._linha(grupo, pontos, "pesado" if nivel >= 3 else "movimentado")
        self._larg_usada = None
        self._ajustar_larguras(self._escala_tela())

    def _linha(self, grupo, pontos, tipo):
        plano = []
        for p in pontos:
            plano.extend(self._local(p[0], p[1]))
        if tipo == "alt":
            grupo.add(Color(0.05, 0.08, 0.11, 0.9))
            grupo.add(Line(points=plano, width=1, joint="round", cap="round"))
            grupo.add(Color(0.55, 0.62, 0.70, 0.95))
            grupo.add(Line(points=plano, width=1, joint="round", cap="round"))
        elif tipo in ("movimentado", "pesado"):
            grupo.add(Color(*(tema.VERMELHO if tipo == "pesado" else tema.LARANJA)))
            grupo.add(Line(points=plano, width=1, joint="round", cap="round"))
        elif tipo == "rota":
            grupo.add(Color(*tema.com_alfa(tema.CIANO, 0.28)))
            grupo.add(Line(points=plano, width=1, joint="round", cap="round"))
            grupo.add(Color(*tema.CIANO))
            grupo.add(Line(points=plano, width=1, joint="round", cap="round"))
        else:
            grupo.add(Color(*tema.com_alfa(tema.LARANJA, 0.85)))
            grupo.add(Line(points=plano, width=1, joint="round", cap="round"))

    def _ajustar_larguras(self, s):
        # largura da Line é em unidades locais: compensa a escala para ficar
        # com a mesma espessura na tela
        if self._larg_usada and abs(s / self._larg_usada - 1) < 0.04:
            return
        self._larg_usada = s
        linhas_rota = [i for i in self._g_rota.children if isinstance(i, Line)]
        for k, linha in enumerate(linhas_rota):   # halo, linha da rota e, depois, os trechos de avenida
            linha.width = (dp(11) if k == 0 else dp(4.2) if k == 1 else dp(4.6)) / s
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
        self._m_halo = grupo(Color(*tema.com_alfa(tema.CIANO, 0.30)), self._e_halo)
        self._seta_malha = Mesh(vertices=[0.0] * 16, indices=[0, 1, 2, 3], mode="triangle_fan")
        self._seta_borda = Line(points=[0.0] * 8, close=True, width=dp(1.4))
        self._m_seta = grupo(Color(*tema.BRANCO), self._seta_malha,
                             Color(*tema.CIANO), self._seta_borda)
        self._e_ponto = [Ellipse(size=(dp(18), dp(18))), Ellipse(size=(dp(12), dp(12)))]
        self._m_ponto = grupo(Color(*tema.BRANCO), self._e_ponto[0],
                              Color(*tema.CIANO), self._e_ponto[1])
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
        if self._destino:
            x, y = self._para_tela(*self._destino)
            for e in self._e_dest:
                e.pos = (x - e.size[0] / 2.0, y - e.size[1] / 2.0)
            quais.append(self._m_dest)
        if self.eu:
            precisao = self.eu[3]
            lat, lon, rumo = self._vista or self.eu[:3]
            x, y = self._para_tela(lat, lon)
            if precisao:
                r = precisao / metros_por_px(lat, self.zoom) * self._escala
                if dp(20) < r < max(self.width, self.height):
                    self._e_prec.pos, self._e_prec.size = (x - r, y - r), (2 * r, 2 * r)
                    quais.append(self._m_prec)
            self._e_halo.pos = (x - dp(22), y - dp(22))
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
        self._em_lote = True
        try:
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
            if self.seguindo and self._vista is not None:
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
            if self._alvo_zoom is not None:
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
        if getattr(touch, "is_mouse_scrolling", False):
            self._alvo_zoom = None
            self._zoom_no_ponto(self.zoom + (0.5 if touch.button == "scrolldown" else -0.5), *touch.pos)
            self._aplicar()
            return True
        self._velocidade = (0.0, 0.0)
        if touch.is_double_tap:
            self._alvo_zoom = None
            self._zoom_no_ponto(self.zoom + 1.0, *touch.pos)
            self._aplicar()
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
                self._alvo_zoom = None
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

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        self._t_mexeu = time.time()
        self._cancelar_segurar()
        if touch in self._toques:
            self._toques.remove(touch)
        # inércia: continua deslizando na velocidade dos últimos movimentos
        agora = time.time()
        recentes = [m for m in self._movs if agora - m[0] < 0.12]
        if not self._toques and len(recentes) >= 2 and not self.seguindo:
            dur = max(agora - recentes[0][0], 1 / 60.0)
            self._velocidade = (sum(m[1] for m in recentes) / dur, sum(m[2] for m in recentes) / dur)
            self._ligar_animacao()
        self._movs = []
        return True
