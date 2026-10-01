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

A 1ª versão usava imagens prontas do OpenStreetMap pintadas por shader:
ficava ilegível no celular (nome pequeno, embaçado no zoom).
"""
import math
import time

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.graphics import (Color, Ellipse, InstructionGroup, Line, Mesh, PopMatrix,
                           PushMatrix, Rectangle, Rotate, Scale, Translate)
from kivy.metrics import Metrics, dp, sp
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import tema
from mapa_vetor import AREAS, FUNDO, RUAS, FonteVetorial, tiles_do_retangulo, z_dados

ZOOM_MIN, ZOOM_MAX = 4.0, 19.0
TAM = 256.0
MAX_ROTULOS_RUA = 30
MAX_ROTULOS_LUGAR = 8
MAX_ROTULOS_POI = 10
REPOSICIONAR_S = 0.45      # refaz a escolha dos nomes no máximo a cada isso
INERCIA = 3.5              # quanto maior, mais rápido o deslize para


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
        self.grupo = InstructionGroup()
        if ponto is not None:
            self.grupo.add(Color(*ponto))
            self.bolinha = Ellipse(size=(dp(10), dp(10)))
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
        deslocar = dp(9) if ponto is not None else -w / 2.0
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
        self.eu = None                      # (lat, lon, rumo ou None, precisão m)
        self._navegando = False
        self._escala = Metrics.density      # px de tela por px do mundo no zoom 14
        self._origem = mundo(self.centro[0], self.centro[1], 14)
        self._rota, self._trilha, self._destino = [], [], None
        self._desenhados = {}               # (dz, tx, ty, rz) -> [(grupo, instrução), ...]
        self._nivel = None                  # (dz, rz) atual
        self._rotulos = []
        self._texturas = {}
        self._t_rotulos = 0.0
        self._ev_rotulos = None
        self._larg_usada = None
        self._quadro = None
        self._alvo = None
        self._alvo_zoom = None
        self._ev_anim = None
        self._toques = []
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
        self._g_trilha = InstructionGroup()
        self._g_rota = InstructionGroup()
        self.canvas.add(self._g_trilha)
        self.canvas.add(self._g_rota)
        self.canvas.add(PopMatrix())
        self._g_rotulos = InstructionGroup()  # nomes, em coordenadas de tela
        self.canvas.add(self._g_rotulos)
        self._g_tela = InstructionGroup()     # seta e destino
        self.canvas.add(self._g_tela)

        # crédito exigido pelos dados
        self.credito = Label(text="(c) OpenStreetMap, OpenFreeMap", font_size=dp(10),
                             color=tema.CIANO_FRACO, size_hint=(None, None), size=(dp(170), dp(16)))
        self.add_widget(self.credito)
        self.credito_margem = (dp(6), dp(4))
        self.bind(pos=self._aplicar, size=self._aplicar, zoom=self._aplicar, rotacao=self._aplicar)

    # --- API usada pelas telas ---------------------------------------------
    def mostrar_eu(self, lat, lon, rumo=None, precisao=None, vel_kmh=None):
        self.eu = (lat, lon, rumo, precisao)
        if self.seguindo:
            rot = self.rotacao
            if self._navegando and self.girar and rumo is not None:
                rot = rumo
            elif not (self._navegando and self.girar):
                rot = 0.0
            if self._navegando and vel_kmh is not None:
                # zoom automático: mais longe quando anda rápido
                self._alvo_zoom = 17.2 - max(0.0, min(1.0, (vel_kmh - 12.0) / 23.0)) * 1.0
            self._animar_para(lat, lon, rot)
        else:
            self._desenhar_tela()

    def recentralizar(self):
        self.seguindo = True
        if self.eu:
            self.mostrar_eu(*self.eu)

    def modo_navegacao(self, ligado):
        self._navegando = ligado
        # navegando e girando: a seta fica mais embaixo, sobra mapa à frente
        self.ancora = (0.5, 0.30) if (ligado and self.girar) else (0.5, 0.5)
        if ligado:
            self.seguindo = True
            self._alvo_zoom = 17.0
        else:
            self._alvo_zoom = None
        if self.eu:
            self.mostrar_eu(*self.eu)
        else:
            self._aplicar()

    def definir_rota(self, pontos):
        self._rota = list(pontos)
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

    def _atualizar_tiles(self):
        rz = int(max(ZOOM_MIN, min(ZOOM_MAX, round(self.zoom))))
        dz = z_dados(rz)
        nivel = (dz, rz)
        xs, ys = [], []
        margem = dp(40)
        for px, py in ((self.x - margem, self.y - margem), (self.right + margem, self.y - margem),
                       (self.x - margem, self.top + margem), (self.right + margem, self.top + margem)):
            lx, ly = self._tela_para_local(px, py)
            xs.append(lx + self._origem[0])
            ys.append(self._origem[1] - ly)
        precisa = {(dz, tx, ty, rz) for tx, ty in tiles_do_retangulo(min(xs), min(ys), max(xs), max(ys), dz)}
        faltando = False
        for chave in precisa:
            if chave in self._desenhados:
                continue
            preparado = self.fonte.pronto(chave)
            if preparado is None:
                self.fonte.pedir(chave)
                faltando = True
            else:
                self._desenhar_tile(chave, preparado)
        for chave in list(self._desenhados):
            mesmo_nivel = (chave[0], chave[3]) == nivel
            # desenho de outro zoom só sai quando o novo já cobriu a tela
            if (mesmo_nivel and chave not in precisa) or (not mesmo_nivel and not faltando):
                self._apagar_tile(chave)
        if nivel != self._nivel:
            self._nivel = nivel
            self._t_rotulos = 0.0

    def _desenhar_tile(self, chave, preparado):
        itens = []
        for nome, listas in preparado["areas"]:
            if not listas:
                continue
            cor = Color(*AREAS[nome])
            self._g_areas.add(cor)
            itens.append((self._g_areas, cor))
            for vertices, indices in listas:
                malha = Mesh(vertices=vertices, indices=indices, mode="triangles")
                self._g_areas.add(malha)
                itens.append((self._g_areas, malha))
        for nome, cor_rua, listas in preparado["ruas"]:
            if not listas:
                continue
            grupo = self._g_ruas[nome]
            cor = Color(*cor_rua)
            grupo.add(cor)
            itens.append((grupo, cor))
            for vertices, indices in listas:
                malha = Mesh(vertices=vertices, indices=indices, mode="triangles")
                grupo.add(malha)
                itens.append((grupo, malha))
        self._desenhados[chave] = itens
        self._t_rotulos = 0.0  # nomes novos disponíveis

    def _apagar_tile(self, chave):
        for grupo, item in self._desenhados.pop(chave, []):
            grupo.remove(item)

    def _tile_pronto(self, chave):
        if (chave[0], chave[3]) == self._nivel:
            self._aplicar()

    # --- nomes --------------------------------------------------------------------
    def _textura(self, texto, tamanho, cor, negrito=True):
        cor = tuple(cor)
        chave = (texto, tamanho, cor, negrito)
        tex = self._texturas.get(chave)
        if tex is None:
            rotulo = CoreLabel(text=texto, font_size=tamanho, bold=negrito, color=cor,
                               outline_width=max(1, int(dp(1.6))), outline_color=FUNDO[:3])
            rotulo.refresh()
            tex = rotulo.texture
            if len(self._texturas) > 400:
                self._texturas.clear()
            self._texturas[chave] = tex
        return tex

    def _pedir_rotulos(self):
        if self._ev_rotulos is None:
            espera = max(0.0, REPOSICIONAR_S - (time.time() - self._t_rotulos))
            self._ev_rotulos = Clock.schedule_once(self._escolher_rotulos, espera)

    def _escolher_rotulos(self, *a):
        """Escolhe quais nomes cabem na tela sem se encostar (mais importante primeiro)."""
        self._ev_rotulos = None
        self._t_rotulos = time.time()
        candidatos = []
        for chave in self._desenhados:
            if (chave[0], chave[3]) != self._nivel:
                continue
            preparado = self.fonte.pronto(chave)
            if preparado:
                candidatos.extend(preparado["rotulos"])
        candidatos.sort(key=lambda r: -r["peso"])
        s = self._escala_tela()
        ocupados, usados_texto, novos = [], {}, []
        conta = {"rua": 0, "lugar": 0, "poi": 0}
        limite = {"rua": MAX_ROTULOS_RUA, "lugar": MAX_ROTULOS_LUGAR, "poi": MAX_ROTULOS_POI}
        x0, y0, x1, y1 = self.x + dp(8), self.y + dp(8), self.right - dp(8), self.top - dp(8)
        for r in candidatos:
            tipo = r["tipo"]
            if conta[tipo] >= limite[tipo]:
                continue
            sx, sy = self._local_para_tela(r["x"], r["y"])
            if not (x0 < sx < x1 and y0 < sy < y1):
                continue
            if tipo == "rua":
                tex = self._textura(r["texto"], sp(13.5) if r["peso"] < 4 else sp(14.5), tema.BRANCO)
                if r["comp"] * s < tex.width * 0.85:
                    continue  # o nome não cabe no trecho
                ang = math.degrees(r["ang"]) + self.rotacao
                ang = (ang + 90.0) % 180.0 - 90.0  # sempre de pé
                ponto = None
            elif tipo == "lugar":
                tex = self._textura(r["texto"], sp(15), (0.72, 0.84, 0.94, 1))
                ang, ponto = 0.0, None
            else:
                tex = self._textura(r["texto"], sp(12.5), (1.0, 0.80, 0.58, 1), negrito=False)
                ang, ponto = 0.0, tema.LARANJA
            w, h = tex.size
            c, sn = abs(math.cos(math.radians(ang))), abs(math.sin(math.radians(ang)))
            bw, bh = w * c + h * sn + dp(6), w * sn + h * c + dp(6)
            cx_ = sx + (w / 2.0 + dp(9) if ponto else 0)
            caixa = (cx_ - bw / 2, sy - bh / 2, cx_ + bw / 2, sy + bh / 2)
            if any(caixa[0] < o[2] and o[0] < caixa[2] and caixa[1] < o[3] and o[1] < caixa[3]
                   for o in ocupados):
                continue
            visto = usados_texto.get(r["texto"])
            if visto and math.hypot(visto[0] - sx, visto[1] - sy) < dp(260):
                continue
            ocupados.append(caixa)
            usados_texto[r["texto"]] = (sx, sy)
            conta[tipo] += 1
            novos.append((r, tex, ponto))
        self._g_rotulos.clear()
        self._rotulos = []
        for r, tex, ponto in novos:
            rot = _Rotulo(r, tex, ponto)
            self._rotulos.append(rot)
            self._g_rotulos.add(rot.grupo)
        self._mover_rotulos()

    def _mover_rotulos(self):
        for rot in self._rotulos:
            r = rot.info
            sx, sy = self._local_para_tela(r["x"], r["y"])
            rot.mover.xy = (sx, sy)
            if r["tipo"] == "rua":
                ang = math.degrees(r["ang"]) + self.rotacao
                rot.girar.angle = (ang + 90.0) % 180.0 - 90.0
            if rot.bolinha is not None:
                rot.bolinha.pos = (sx - dp(5), sy - dp(5))

    # --- rota, trilha, destino e seta ---------------------------------------------
    def _refazer_linhas(self, so_trilha=False):
        grupos = [(self._g_trilha, self._trilha, "trilha")]
        if not so_trilha:
            grupos.append((self._g_rota, self._rota, "rota"))
        for grupo, pontos, tipo in grupos:
            grupo.clear()
            if len(pontos) < 2:
                continue
            plano = []
            for lat, lon in pontos:
                plano.extend(self._local(lat, lon))
            if tipo == "rota":
                grupo.add(Color(*tema.com_alfa(tema.CIANO, 0.28)))
                grupo.add(Line(points=plano, width=1, joint="round", cap="round"))
                grupo.add(Color(*tema.CIANO))
                grupo.add(Line(points=plano, width=1, joint="round", cap="round"))
            else:
                grupo.add(Color(*tema.com_alfa(tema.LARANJA, 0.85)))
                grupo.add(Line(points=plano, width=1, joint="round", cap="round"))
        self._larg_usada = None
        self._ajustar_larguras(self._escala_tela())

    def _ajustar_larguras(self, s):
        # largura da Line é em unidades locais: compensa a escala para ficar
        # com a mesma espessura na tela
        if self._larg_usada and abs(s / self._larg_usada - 1) < 0.04:
            return
        self._larg_usada = s
        linhas_rota = [i for i in self._g_rota.children if isinstance(i, Line)]
        for linha, px in zip(linhas_rota, (dp(11), dp(4.2))):
            linha.width = px / s
        for linha in (i for i in self._g_trilha.children if isinstance(i, Line)):
            linha.width = dp(2.6) / s

    def _desenhar_tela(self):
        g = self._g_tela
        g.clear()
        if self._destino:
            x, y = self._para_tela(*self._destino)
            g.add(Color(*tema.com_alfa(tema.LARANJA, 0.3)))
            g.add(Ellipse(pos=(x - dp(16), y - dp(16)), size=(dp(32), dp(32))))
            g.add(Color(*tema.LARANJA))
            g.add(Ellipse(pos=(x - dp(9), y - dp(9)), size=(dp(18), dp(18))))
            g.add(Color(*tema.FUNDO))
            g.add(Ellipse(pos=(x - dp(4), y - dp(4)), size=(dp(8), dp(8))))
        if not self.eu:
            return
        lat, lon, rumo, precisao = self.eu
        x, y = self._para_tela(lat, lon)
        if precisao:
            r = precisao / metros_por_px(lat, self.zoom) * self._escala
            if dp(20) < r < max(self.width, self.height):
                g.add(Color(*tema.com_alfa(tema.CIANO, 0.10)))
                g.add(Ellipse(pos=(x - r, y - r), size=(2 * r, 2 * r)))
        g.add(Color(*tema.com_alfa(tema.CIANO, 0.30)))
        g.add(Ellipse(pos=(x - dp(22), y - dp(22)), size=(dp(44), dp(44))))
        if rumo is None:
            g.add(Color(*tema.BRANCO))
            g.add(Ellipse(pos=(x - dp(9), y - dp(9)), size=(dp(18), dp(18))))
            g.add(Color(*tema.CIANO))
            g.add(Ellipse(pos=(x - dp(6), y - dp(6)), size=(dp(12), dp(12))))
            return
        # seta: ângulo na tela = rumo - rotação do mapa (horário a partir de cima)
        ang = -(rumo - self.rotacao)
        forma = [(0, dp(19)), (dp(13), -dp(13)), (0, -dp(5)), (-dp(13), -dp(13))]
        pts = []
        for px, py in forma:
            rx, ry = _girar(px, py, ang)
            pts.append((x + rx, y + ry))
        vert = []
        for px, py in pts:
            vert += [px, py, 0, 0]
        g.add(Color(*tema.BRANCO))
        g.add(Mesh(vertices=vert, indices=[0, 1, 2, 3], mode="triangle_fan"))
        g.add(Color(*tema.CIANO))
        g.add(Line(points=[c for p in pts for c in p], close=True, width=dp(1.4)))

    # --- animação (câmera seguindo, zoom suave, inércia) -----------------------------
    def _animar_para(self, lat, lon, rot):
        self._alvo = (lat, lon, rot)
        self._ligar_animacao()

    def _ligar_animacao(self):
        if self._ev_anim is None:
            self._ev_anim = Clock.schedule_interval(self._passo_animacao, 1 / 60.0)

    def _parar_animacao(self):
        if self._ev_anim is not None:
            self._ev_anim.cancel()
            self._ev_anim = None
        self._alvo = None
        self._velocidade = (0.0, 0.0)

    def _passo_animacao(self, dt):
        dt = min(dt, 0.1)
        k = 1.0 - math.exp(-dt * 5.0)
        mexeu = False
        if self._alvo is not None and self.seguindo:
            lat, lon, rot = self._alvo
            clat, clon = self.centro
            self.centro = (clat + (lat - clat) * k, clon + (lon - clon) * k)
            d_rot = _dif_angulo(self.rotacao, rot)
            self.rotacao = (self.rotacao + d_rot * k) % 360.0
            if abs(lat - clat) < 1e-7 and abs(lon - clon) < 1e-7 and abs(d_rot) < 0.2:
                self.centro = (lat, lon)
                self._alvo = None
            mexeu = True
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
        self._aplicar()
        if not mexeu:
            self._ev_anim = None
            return False

    # --- toque: arrastar, pinça, duplo toque, rodinha do mouse -----------------
    def _arrastar(self, dx, dy):
        s = self._escala_tela()
        gx, gy = _girar(dx, dy, -self.rotacao)
        cx, cy = self._local(*self.centro)
        self.centro = self._local_para_geo(cx - gx / s, cy - gy / s)

    def _zoom_no_ponto(self, novo_zoom, sx, sy):
        """Muda o zoom mantendo parado o ponto da tela (sx, sy) (sob os dedos)."""
        antes = self._tela_para_local(sx, sy)
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, novo_zoom))
        depois = self._tela_para_local(sx, sy)
        cx, cy = self._local(*self.centro)
        self.centro = self._local_para_geo(cx + antes[0] - depois[0], cy + antes[1] - depois[1])

    def _sair_do_seguir(self):
        if self.seguindo:
            self.seguindo = False
        self._alvo = None
        if not self._navegando:
            self._alvo_zoom = None

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        if super().on_touch_down(touch):
            return True
        if getattr(touch, "is_mouse_scrolling", False):
            self._alvo_zoom = None
            self._zoom_no_ponto(self.zoom + (0.5 if touch.button == "scrolldown" else -0.5), *touch.pos)
            if not self.seguindo:
                pass
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
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
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
