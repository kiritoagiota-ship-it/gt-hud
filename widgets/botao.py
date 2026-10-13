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
from kivy.app import App
from kivy.graphics import Color, Line, Mesh, PopMatrix, PushMatrix, Scale, Translate
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.button import Button

import android_utils
import tema
from widgets import icones

_degrade = {}
VIBRA_TOQUE_MS = 12
VIBRA_TOQUE_FORCA = 70
AFUNDA = 0.055            # quanto o botão encolhe apertado (5,5%)


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


_faixa_monarca = []


def faixa_monarca():
    """Textura 64x1 do azul ao roxo (escuros o bastante para o texto branco ler no sol):
    o corpo dos botões cheios no tema Monarca (pedido do dono, 12/10/2026: caprichar na
    estética do Monarca)."""
    if not _faixa_monarca:
        n = 64
        de, para = (0.13, 0.36, 0.90), (0.50, 0.22, 0.93)
        dados = bytearray()
        for k in range(n):
            f = k / (n - 1.0)
            dados += bytes([int(255 * (a + (b - a) * f)) for a, b in zip(de, para)] + [255])
        tex = Texture.create(size=(n, 1), colorfmt="rgba")
        tex.blit_buffer(bytes(dados), colorfmt="rgba", bufferfmt="ubyte")
        tex.wrap = "clamp_to_edge"
        _faixa_monarca.append(tex)
    return _faixa_monarca[0]


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


def mexer(w):
    """(deslocamento, escala) do desenho INTEIRO do widget `w` (o fundo, o texto, os
    filhos): para animar sem mexer na posição de verdade (o toque e o layout seguem no
    lugar). Postos uma vez só, em volta de tudo que o widget desenha."""
    par = getattr(w, "_mexer", None)
    if par is None:
        w.canvas.before, w.canvas.after   # (os dois grupos precisam existir antes: entram no meio)
        par = w._mexer = (Translate(0, 0), Scale(1, 1, 1))
        w.canvas.insert(0, PushMatrix())
        w.canvas.insert(1, par[0])
        w.canvas.insert(2, par[1])
        w.canvas.insert(len(w.canvas.children), PopMatrix())   # (no fim MESMO: add() poria antes do canvas.after)
    par[1].origin = w.center
    return par


def vibrar_toque():
    android_utils.vibrar([0, VIBRA_TOQUE_MS], [0, VIBRA_TOQUE_FORCA])


class BotaoHUD(Button):
    destaque = BooleanProperty(False)
    cor = ListProperty(tema.CIANO)
    opaco = BooleanProperty(False)  # por cima do mapa: fundo escuro, senão some na rua clara
    brilho = NumericProperty(0.0)   # 1 = recém-tocado; cai a 0 depois de soltar
    aperto = NumericProperty(0.0)   # 1 = apertado (o botão encolhe um pouco); negativo = estufado
    icone = StringProperty("")      # desenho de widgets/icones.py (o texto, se houver, vai embaixo)
    plano = BooleanProperty(False)  # sem corpo nem borda: está dentro de uma coluna que já tem os dela

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
        self._aura = False
        self._halo_base = 0.0
        self._anim = None
        self.bind(pos=self._desenhar, size=self._desenhar, destaque=self._desenhar, cor=self._desenhar,
                  opaco=self._desenhar, disabled=self._desenhar, state=self._ao_tocar,
                  brilho=self._pintar_brilho, icone=self._desenhar, text=self._desenhar,
                  aperto=self._apertar, plano=self._desenhar)
        self._desenhar()

    def _ao_tocar(self, *a):
        if self._anim is not None:
            self._anim.cancel(self)
            self._anim = None
        if self.state == "down":
            self.brilho = 1.0
            self.aperto = 1.0   # afunda na hora (pedido do dono, 09/10/2026) e volta com um quique ao soltar
            vibrar_toque()
            tocador = getattr(App.get_running_app(), "sons", None)
            if tocador is not None:
                tocador.tocar("toque")
        else:
            self._anim = (Animation(brilho=0.0, d=0.28, t="out_quad")
                          & Animation(aperto=0.0, d=0.24, t="out_back"))
            self._anim.start(self)

    def _apertar(self, *a):
        escala = mexer(self)[1]
        escala.x = escala.y = 1.0 - AFUNDA * self.aperto

    def pulsar(self):
        """Acende e dá um pulinho sem ser tocado: confirma que algo foi anotado."""
        if self._anim is not None:
            self._anim.cancel(self)
        self.brilho, self.aperto = 1.0, -2.2
        self._anim = (Animation(brilho=0.0, d=0.6, t="out_quad")
                      & Animation(aperto=0.0, d=0.42, t="out_back"))
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
        self._aura = False
        with self.canvas.before:
            if self.plano:
                # dentro de uma coluna (telas/mapa.Doca): só o clarão do toque; o resto é da coluna
                self._cor_halo = Color(0, 0, 0, 0)
                self._cor_toque = Color(0, 0, 0, 0)
                Mesh(vertices=[v for px, py in ((x + dp(3), y + dp(2)), (x + w - dp(3), y + dp(2)),
                                               (x + w - dp(3), y + h - dp(2)), (x + dp(3), y + h - dp(2)))
                               for v in (px, py, 0, 0)],
                     indices=[0, 1, 2, 3], mode="triangle_fan")
            else:
                self._corpo(pts, plano, c, x, y, w, h, apagado)
        self._texto_e_icone(x, y, w, h, apagado, self._aura)

    def _corpo(self, pts, plano, c, x, y, w, h, apagado):
        """Sombra, halo, corpo, clarão do toque, borda e cantos (dentro de `with canvas.before`)."""
        if self.opaco or self.destaque:
            # relevo: uma sombra por baixo, para o botão se destacar do mapa
            Color(0, 0, 0, 0.36 * apagado)
            sombra = []
            for px, py in _poligono(x - dp(1), y - dp(3.5), w + dp(2), h + dp(1.5), c):
                sombra += [px, py, 0, 0]
            Mesh(vertices=sombra, indices=list(range(len(pts))), mode="triangle_fan")
        # halo
        self._cor_halo = Color(*tema.com_alfa(self.cor, self._halo_base))
        Line(points=plano, close=True, width=dp(3.4), joint="round")
        # corpo
        # (Monarca: o botão cheio da cor do tema vira um degradê do azul ao roxo, texto branco)
        do_tema = list(self.cor[:3]) == list(tema.CIANO[:3])
        aura = self._aura = self.destaque and tema.monarca() and do_tema
        if aura:
            Color(1, 1, 1, apagado)
            vert = []
            for px, py in pts:
                vert += [px, py, (px - x) / w if w else 0.0, 0.5]
            Mesh(vertices=vert, indices=list(range(len(pts))), mode="triangle_fan", texture=faixa_monarca())
            Color(1, 1, 1, 0.22 * apagado)          # um fio de luz na beira de cima
            Line(points=[x + c, y + h - dp(1.5), x + w - dp(2), y + h - dp(1.5)], width=dp(1))
        elif self.destaque:
            Color(*tema.com_alfa(self.cor, apagado))
            malha_degrade(pts, y, h, 0.86)   # cheio: degradê leve, a cor não pode perder força
        else:
            Color(*tema.com_alfa(tema.PAINEL_CLARO, (0.96 if self.opaco else 0.55) * apagado))
            malha_degrade(pts, y, h)
            Color(1, 1, 1, 0.10 * apagado)           # um fio de luz na beira de cima
            Line(points=[x + c, y + h - dp(1.6), x + w - dp(2), y + h - dp(1.6)], width=dp(1))
        # toque (acende e apaga)
        self._cor_toque = Color(0, 0, 0, 0)
        vert = []
        for px, py in pts:
            vert += [px, py, 0, 0]
        Mesh(vertices=vert, indices=list(range(len(pts))), mode="triangle_fan")
        # borda e cantos
        Color(*tema.com_alfa(self.cor, apagado))
        Line(points=plano, close=True, width=dp(1.2))
        if tema.monarca() and do_tema and not self.destaque:
            Color(*tema.com_alfa(tema.ROXO, apagado))   # os dois cantos cortados no roxo da aura
        for traco in cantos(pts, c):
            Line(points=traco, width=dp(2.1), cap="square", joint="miter")

    def _texto_e_icone(self, x, y, w, h, apagado, aura):
        texto = tema.BRANCO if aura else (tema.FUNDO if self.destaque else self.cor)
        self.canvas.after.clear()
        if self.icone:
            # com texto: ícone em cima e o nome pequeno embaixo; sem texto: só o ícone, no meio
            com_texto = bool(self.text)
            tam = min(w, h) * (0.40 if com_texto else 0.50)
            cy = y + h * (0.62 if com_texto else 0.5)
            with self.canvas.after:
                # (o mesmo desenho maior e fraco por baixo: um brilho em volta do ícone)
                icones.desenhar(self.icone, x + w / 2.0, cy, tam * 1.16, tema.com_alfa(texto, 0.20 * apagado))
                icones.desenhar(self.icone, x + w / 2.0, cy, tam, tema.com_alfa(texto, apagado))
            self.text_size = (w, h)
            self.halign, self.valign = "center", "bottom"
            self.padding = (0, dp(5))
        self.color = texto
        self.disabled_color = tema.com_alfa(texto, 0.55 if self.destaque else 0.4)
        self._pintar_brilho()
