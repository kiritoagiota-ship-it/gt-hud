"""Botão com cantos cortados (estilo HUD).

Visual (06/10/2026, o dono pediu capricho no design e efeitos):
- halo: um brilho largo e fraco em volta da borda;
- corpo em degradê (mais claro em cima), não mais cor chapada;
- os dois cantos cortados ganham um traço mais grosso (detalhe de HUD);
- ao tocar: o botão acende na hora, vibra de leve e o brilho se apaga
  aos poucos depois de soltar (dá para SENTIR e VER que o toque pegou,
  importante com a bike tremendo);
- desativado: tudo apagado.

Custo: o desenho só é refeito quando muda tamanho/estado; a animação do
toque mexe em duas cores já criadas (nada é redesenhado por quadro).
"""
from kivy.animation import Animation
from kivy.graphics import Color, Line, Mesh
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty
from kivy.uix.button import Button

import android_utils
import tema

_degrade = {}
VIBRA_TOQUE_MS = 12
VIBRA_TOQUE_FORCA = 70


def degrade(base=None):
    """Textura 1x32 de claro (em cima) para escuro (`base` = quanto sobra da
    cor embaixo): multiplicada pela cor do desenho, vira o degradê dela."""
    base = tema.degrade_base if base is None else base
    tex = _degrade.get(base)
    if tex is None:
        n = 32
        dados = bytearray()
        for k in range(n):               # k = 0 é a base
            f = k / (n - 1.0)
            v = int(255 * (base + (1.0 - base) * f * f))
            dados += bytes((v, v, v, 255))
        tex = _degrade[base] = Texture.create(size=(1, n), colorfmt="rgba")
        tex.blit_buffer(bytes(dados), colorfmt="rgba", bufferfmt="ubyte")
        tex.wrap = "clamp_to_edge"
    return tex


def _poligono(x, y, w, h, c):
    # corta o canto superior esquerdo e o inferior direito
    return [(x + c, y + h), (x + w, y + h), (x + w, y + c),
            (x + w - c, y), (x, y), (x, y + h - c)]


def malha_degrade(pts, y, h, base=None):
    """Mesh do polígono com o degradê de cima a baixo."""
    vert = []
    for px, py in pts:
        vert += [px, py, 0.5, (py - y) / h if h else 0.0]
    return Mesh(vertices=vert, indices=list(range(len(pts))), mode="triangle_fan", texture=degrade(base))


def cantos(pts, c):
    """Traços grossos nos dois cantos cortados: [pontos da linha, ...]."""
    (ax, ay), _, (cx, cy), (dx, dy), _, (fx, fy) = pts
    e = c * 0.9   # quanto o traço avança pelos lados depois do corte
    return [[fx, fy - e, fx, fy, ax, ay, ax + e, ay],
            [cx, cy + e, cx, cy, dx, dy, dx - e, dy]]


def vibrar_toque():
    android_utils.vibrar([0, VIBRA_TOQUE_MS], [0, VIBRA_TOQUE_FORCA])


class BotaoHUD(Button):
    destaque = BooleanProperty(False)
    cor = ListProperty(tema.CIANO)
    opaco = BooleanProperty(False)  # por cima do mapa: fundo escuro, senão some na rua clara
    brilho = NumericProperty(0.0)   # 1 = recém-tocado; cai a 0 depois de soltar

    def __init__(self, **kw):
        kw.setdefault("font_size", tema.T_BOTAO)
        kw.setdefault("bold", True)
        super().__init__(**kw)
        self.background_normal = ""
        self.background_down = ""
        self.background_disabled_normal = ""
        self.background_disabled_down = ""
        self.background_color = (0, 0, 0, 0)
        self._cor_toque = self._cor_halo = None
        self._anim = None
        self.bind(pos=self._desenhar, size=self._desenhar, destaque=self._desenhar, cor=self._desenhar,
                  opaco=self._desenhar, disabled=self._desenhar, state=self._ao_tocar,
                  brilho=self._pintar_brilho)
        self._desenhar()

    def _ao_tocar(self, *a):
        if self._anim is not None:
            self._anim.cancel(self)
            self._anim = None
        if self.state == "down":
            self.brilho = 1.0
            vibrar_toque()
        else:
            self._anim = Animation(brilho=0.0, d=0.28, t="out_quad")
            self._anim.start(self)

    def _pintar_brilho(self, *a):
        if self._cor_toque is None:
            return
        b = self.brilho
        if self.destaque:   # botão cheio: clareia para o branco
            self._cor_toque.rgba = (1, 1, 1, 0.45 * b)
        else:
            self._cor_toque.rgba = tema.com_alfa(self.cor, 0.38 * b)
        self._cor_halo.rgba = tema.com_alfa(self.cor, self._halo_base + 0.30 * b)

    def _desenhar(self, *a):
        c = min(dp(12), self.height * 0.3)
        x, y, w, h = self.x, self.y, self.width, self.height
        pts = _poligono(x, y, w, h, c)
        plano = [v for p in pts for v in p]
        apagado = 0.35 if self.disabled else 1.0
        self._halo_base = (0.20 if self.destaque else 0.12) * apagado
        self.canvas.before.clear()
        with self.canvas.before:
            # halo
            self._cor_halo = Color(*tema.com_alfa(self.cor, self._halo_base))
            Line(points=plano, close=True, width=dp(3.4), joint="round")
            # corpo
            if self.destaque:
                Color(*tema.com_alfa(self.cor, apagado))
                malha_degrade(pts, y, h, 0.86)   # cheio: degradê leve, a cor não pode perder força
            else:
                Color(*tema.com_alfa(tema.PAINEL_CLARO, (0.96 if self.opaco else 0.55) * apagado))
                malha_degrade(pts, y, h)
            # toque (acende e apaga)
            self._cor_toque = Color(0, 0, 0, 0)
            vert = []
            for px, py in pts:
                vert += [px, py, 0, 0]
            Mesh(vertices=vert, indices=list(range(len(pts))), mode="triangle_fan")
            # borda e cantos
            Color(*tema.com_alfa(self.cor, apagado))
            Line(points=plano, close=True, width=dp(1.2))
            for traco in cantos(pts, c):
                Line(points=traco, width=dp(2.1), cap="square", joint="miter")
        texto = tema.FUNDO if self.destaque else self.cor
        self.color = texto
        self.disabled_color = tema.com_alfa(texto, 0.55 if self.destaque else 0.4)
        self._pintar_brilho()
