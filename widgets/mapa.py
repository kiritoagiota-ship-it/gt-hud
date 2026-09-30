"""Mapa do GT-HUD: tiles do OpenStreetMap pintados no tema do app (shader),
rota, trilha, destino e a seta de quem está pedalando.

Coordenadas "locais" = pixels do Web Mercator no zoom inteiro zi (tile de
256), relativos a uma origem fixada quando o zi muda (o float do OpenGL
perde precisão com números grandes; Y invertido porque no Kivy Y sobe).
Mexer no mapa (arrastar, seguir, girar, zoom fracionário) só altera 4
instruções de matriz; tiles e linhas só são refeitos quando o conjunto
visível ou o zi mudam.
"""
import math
import os

from kivy.clock import Clock
from kivy.graphics import (Color, Ellipse, InstructionGroup, Line, Mesh, PopMatrix,
                           PushMatrix, Rectangle, RenderContext, Rotate, Scale, Translate)
from kivy.metrics import Metrics, dp
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import tema
from mapa_tiles import Tiles

TAM = 256
ZOOM_MIN, ZOOM_MAX = 4.0, 19.0

# Tile claro do OpenStreetMap -> escuro no tema do app: inverte a luz, tira a
# cor e pinta de azul-petróleo (ruas claras viram ciano apagado).
SHADER_TILES = """$HEADER$
void main(void) {
    vec4 c = texture2D(texture0, tex_coord0);
    float l = 1.0 - dot(c.rgb, vec3(0.299, 0.587, 0.114));
    l = clamp((l - 0.5) * 1.35 + 0.5, 0.0, 1.0);
    vec3 escura = vec3(0.016, 0.027, 0.043);
    vec3 media = vec3(0.051, 0.204, 0.251);
    vec3 clara = vec3(0.55, 0.88, 0.94);
    vec3 cor = l < 0.588 ? mix(escura, media, l / 0.588)
                         : mix(media, clara, (l - 0.588) / 0.412);
    gl_FragColor = vec4(cor, 1.0) * frag_color;
}
"""


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
        self._zi = None
        self._origem = (0.0, 0.0)
        self._rects = {}
        self._sem_imagem = set()   # tiles na tela ainda sem imagem baixada
        self._rota = []
        self._trilha = []
        self._destino = None
        self._alvo = None                   # (lat, lon, rotação, zoom) para a animação
        self._ev_anim = None
        self._toques = []
        self._escala_tile = max(1.0, Metrics.density * 0.5)  # tile um pouco maior no celular
        self._larg_usada = None
        self.tiles = Tiles(pasta_cache, self._tile_chegou)

        with self.canvas:
            Color(*tema.FUNDO)
            self._fundo = Rectangle()
            PushMatrix()
            self._m_ancora = Translate(0, 0)
            self._m_rot = Rotate(angle=0, axis=(0, 0, 1))
            self._m_esc = Scale(1, 1, 1)
            self._m_centro = Translate(0, 0)
        self._rc = RenderContext(use_parent_projection=True, use_parent_modelview=True,
                                 use_parent_frag_modelview=True)
        self._rc.shader.fs = SHADER_TILES
        self.canvas.add(self._rc)
        self._g_trilha = InstructionGroup()
        self._g_rota = InstructionGroup()
        self.canvas.add(self._g_trilha)
        self.canvas.add(self._g_rota)
        self.canvas.add(PopMatrix())
        self._g_tela = InstructionGroup()  # seta e destino, em coordenadas de tela
        self.canvas.add(self._g_tela)

        # crédito exigido pelo OpenStreetMap
        self.credito = Label(text="(c) OpenStreetMap", font_size=dp(10), color=tema.CIANO_FRACO,
                             size_hint=(None, None), size=(dp(110), dp(16)))
        self.add_widget(self.credito)
        self.credito_margem = (dp(6), dp(4))

        self.bind(pos=self._aplicar, size=self._aplicar, zoom=self._aplicar,
                  rotacao=self._aplicar)

    # --- API usada pelas telas ---------------------------------------------
    def mostrar_eu(self, lat, lon, rumo=None, precisao=None):
        self.eu = (lat, lon, rumo, precisao)
        if self.seguindo:
            rot = self.rotacao
            if self._navegando and self.girar and rumo is not None:
                rot = rumo
            elif not (self._navegando and self.girar):
                rot = 0.0
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
            self.zoom = 17.0
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
        larg = max((livre_w - 2 * margem) / self._escala_tile, 10)
        alt = max((livre_h - 2 * margem) / self._escala_tile, 10)
        z = math.log2(min(larg / max(x1 - x0, 1e-9), alt / max(y1 - y0, 1e-9)))
        self.seguindo = False
        self.ancora = ((esq + livre_w / 2.0) / max(self.width, 1),
                       (baixo + livre_h / 2.0) / max(self.height, 1))
        self._parar_animacao()
        self.centro = meio
        self.rotacao = 0.0
        self.zoom = max(ZOOM_MIN, min(17.0, z))
        self._aplicar()

    def mudar_zoom(self, delta):
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom + delta))

    # --- conversões -----------------------------------------------------------
    def _local(self, lat, lon):
        wx, wy = mundo(lat, lon, self._zi)
        return wx - self._origem[0], -(wy - self._origem[1])

    def _escala(self):
        return self._escala_tile * 2.0 ** (self.zoom - self._zi)

    def _ancora_px(self):
        return self.x + self.width * self.ancora[0], self.y + self.height * self.ancora[1]

    def _para_tela(self, lat, lon):
        lx, ly = self._local(lat, lon)
        cx, cy = self._local(*self.centro)
        s = self._escala()
        dx, dy = _girar((lx - cx) * s, (ly - cy) * s, self.rotacao)
        ax, ay = self._ancora_px()
        return ax + dx, ay + dy

    # --- desenho ----------------------------------------------------------------
    def _aplicar(self, *a):
        if self.width < 2 or self.height < 2:
            return
        self._fundo.pos, self._fundo.size = self.pos, self.size
        self.credito.pos = (self.right - self.credito.width - self.credito_margem[0],
                            self.y + self.credito_margem[1])
        z = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom))
        zi = int(z + 0.5)
        if zi != self._zi:
            self._trocar_zi(zi)
        s = self._escala()
        cx, cy = self._local(*self.centro)
        ax, ay = self._ancora_px()
        self._m_ancora.xy = (ax, ay)
        self._m_rot.angle = self.rotacao
        self._m_esc.xyz = (s, s, 1)
        self._m_centro.xy = (-cx, -cy)
        self._atualizar_tiles(s, ax, ay, cx, cy)
        self._ajustar_larguras(s)
        self._desenhar_tela()

    def _trocar_zi(self, zi):
        self._zi = zi
        self._origem = mundo(self.centro[0], self.centro[1], zi)
        self._rc.clear()
        self._rc.add(Color(1, 1, 1, 1))
        self._rects = {}
        self._sem_imagem = set()
        self._refazer_linhas()

    def _atualizar_tiles(self, s, ax, ay, cx, cy):
        # cantos da tela -> coordenadas locais (desfaz âncora, giro e escala)
        xs, ys = [], []
        for px, py in ((self.x, self.y), (self.right, self.y),
                       (self.x, self.top), (self.right, self.top)):
            dx, dy = _girar(px - ax, py - ay, -self.rotacao)
            xs.append(cx + dx / s)
            ys.append(cy + dy / s)
        ox, oy = self._origem
        n = 2 ** self._zi
        tx0 = int(math.floor((min(xs) + ox) / TAM))
        tx1 = int(math.floor((max(xs) + ox) / TAM))
        ty0 = max(0, int(math.floor((oy - max(ys)) / TAM)))
        ty1 = min(n - 1, int(math.floor((oy - min(ys)) / TAM)))
        precisa = {(tx, ty) for tx in range(tx0, tx1 + 1) for ty in range(ty0, ty1 + 1)}
        for chave in list(self._rects):
            if chave not in precisa:
                self._rc.remove(self._rects.pop(chave))
                self._sem_imagem.discard(chave)
        for tx, ty in precisa:
            if (tx, ty) not in self._rects:
                ret = Rectangle(pos=(tx * TAM - ox, -((ty + 1) * TAM - oy)), size=(TAM, TAM))
                self._rc.add(ret)
                self._rects[(tx, ty)] = ret
                self._sem_imagem.add((tx, ty))
        for tx, ty in list(self._sem_imagem):
            tex = self.tiles.textura(self._zi, tx % n, ty)  # pede se ainda não tem
            if tex is not None:
                self._rects[(tx, ty)].texture = tex
                self._sem_imagem.discard((tx, ty))

    def _tile_chegou(self, chave):
        z, x, y = chave
        if z != self._zi:
            return
        n = 2 ** z
        for (tx, ty), ret in self._rects.items():
            if ty == y and tx % n == x:
                ret.texture = self.tiles.textura(z, x, y)
                self._sem_imagem.discard((tx, ty))

    def _refazer_linhas(self, so_trilha=False):
        if self._zi is None:
            return
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
                grupo.add(Color(*tema.com_alfa(tema.CIANO, 0.25)))
                grupo.add(Line(points=plano, width=1, joint="round", cap="round"))
                grupo.add(Color(*tema.CIANO))
                grupo.add(Line(points=plano, width=1, joint="round", cap="round"))
            else:
                grupo.add(Color(*tema.com_alfa(tema.LARANJA, 0.85)))
                grupo.add(Line(points=plano, width=1, joint="round", cap="round"))
        self._larg_usada = None
        self._ajustar_larguras(self._escala())

    def _ajustar_larguras(self, s):
        # a largura da Line é em unidades locais: compensa a escala para
        # continuar com a mesma espessura na tela
        if self._larg_usada and abs(s / self._larg_usada - 1) < 0.04:
            return
        self._larg_usada = s
        linhas_rota = [i for i in self._g_rota.children if isinstance(i, Line)]
        for linha, px in zip(linhas_rota, (dp(9), dp(3.2))):
            linha.width = px / s
        for linha in (i for i in self._g_trilha.children if isinstance(i, Line)):
            linha.width = dp(2.2) / s

    def _desenhar_tela(self):
        g = self._g_tela
        g.clear()
        if self._zi is None:
            return
        if self._destino:
            x, y = self._para_tela(*self._destino)
            g.add(Color(*tema.com_alfa(tema.LARANJA, 0.3)))
            g.add(Ellipse(pos=(x - dp(14), y - dp(14)), size=(dp(28), dp(28))))
            g.add(Color(*tema.LARANJA))
            g.add(Ellipse(pos=(x - dp(8), y - dp(8)), size=(dp(16), dp(16))))
            g.add(Color(*tema.FUNDO))
            g.add(Ellipse(pos=(x - dp(3.5), y - dp(3.5)), size=(dp(7), dp(7))))
        if not self.eu:
            return
        lat, lon, rumo, precisao = self.eu
        x, y = self._para_tela(lat, lon)
        if precisao:
            r = precisao / metros_por_px(lat, self.zoom) * self._escala_tile
            if dp(18) < r < max(self.width, self.height):
                g.add(Color(*tema.com_alfa(tema.CIANO, 0.10)))
                g.add(Ellipse(pos=(x - r, y - r), size=(2 * r, 2 * r)))
        g.add(Color(*tema.com_alfa(tema.CIANO, 0.28)))
        g.add(Ellipse(pos=(x - dp(20), y - dp(20)), size=(dp(40), dp(40))))
        if rumo is None:
            g.add(Color(*tema.BRANCO))
            g.add(Ellipse(pos=(x - dp(8), y - dp(8)), size=(dp(16), dp(16))))
            g.add(Color(*tema.CIANO))
            g.add(Ellipse(pos=(x - dp(5), y - dp(5)), size=(dp(10), dp(10))))
            return
        # seta: ângulo na tela = rumo - rotação do mapa (horário a partir de cima)
        ang = -(rumo - self.rotacao)
        forma = [(0, dp(17)), (dp(12), -dp(12)), (0, -dp(5)), (-dp(12), -dp(12))]
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
        g.add(Line(points=[c for p in pts for c in p], close=True, width=dp(1.3)))

    # --- animação suave (câmera seguindo o GPS) ------------------------------
    def _animar_para(self, lat, lon, rot):
        self._alvo = (lat, lon, rot)
        if self._ev_anim is None:
            self._ev_anim = Clock.schedule_interval(self._passo_animacao, 1 / 30.0)

    def _parar_animacao(self):
        if self._ev_anim is not None:
            self._ev_anim.cancel()
            self._ev_anim = None
        self._alvo = None

    def _passo_animacao(self, dt):
        if self._alvo is None or not self.seguindo:
            self._parar_animacao()
            return False
        lat, lon, rot = self._alvo
        k = 1.0 - math.exp(-dt * 5.0)
        clat, clon = self.centro
        self.centro = (clat + (lat - clat) * k, clon + (lon - clon) * k)
        d_rot = _dif_angulo(self.rotacao, rot)
        nova_rot = (self.rotacao + d_rot * k) % 360.0
        perto = (abs(lat - clat) < 1e-7 and abs(lon - clon) < 1e-7 and abs(d_rot) < 0.2)
        if perto:
            self.centro = (lat, lon)
            nova_rot = rot % 360.0
        if nova_rot != self.rotacao:
            self.rotacao = nova_rot   # dispara _aplicar
        else:
            self._aplicar()
        if perto:
            self._parar_animacao()
            return False

    # --- toque: arrastar, pinça, duplo toque, rodinha do mouse -----------------
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        if super().on_touch_down(touch):
            return True
        if getattr(touch, "is_mouse_scrolling", False):
            self.mudar_zoom(0.5 if touch.button == "scrolldown" else -0.5)
            return True
        if touch.is_double_tap:
            self.mudar_zoom(1.0)
            return True
        touch.grab(self)
        self._toques.append(touch)
        touch.ud["mapa_inicio"] = touch.pos
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
                self.mudar_zoom(math.log2(agora / antes))
            return True
        x0, y0 = touch.ud.get("mapa_inicio", touch.pos)
        if self.seguindo and math.hypot(touch.x - x0, touch.y - y0) < dp(8):
            return True  # tremidinha do dedo não tira do modo seguir
        if self.seguindo:
            self.seguindo = False
            self._parar_animacao()
        s = self._escala()
        dx, dy = _girar(touch.dx, touch.dy, -self.rotacao)
        cx, cy = self._local(*self.centro)
        cx, cy = cx - dx / s, cy - dy / s
        self.centro = geo(cx + self._origem[0], self._origem[1] - cy, self._zi)
        self._aplicar()
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        if touch in self._toques:
            self._toques.remove(touch)
        return True
