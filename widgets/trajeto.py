"""Desenho do caminho da viagem (sem mapa de fundo: funciona sem internet).

As posições viram x/y em metros (projeção plana, mais que suficiente para
os poucos km de uma viagem de bike) com a MESMA escala nos dois eixos, para
o desenho não sair esticado. Norte para cima. Trechos acima do limite de
velocidade ficam laranja; embaixo, uma régua mostra a escala.
"""
import math

from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.metrics import dp
from kivy.properties import ListProperty, NumericProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import tema

M_POR_GRAU_LAT = 110540.0
M_POR_GRAU_LON = 111320.0
AREA_MINIMA_M = 50.0  # parado no lugar, o ruído do GPS não vira um "zoom" gigante
REGUAS_M = (10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000)


def _texto_regua(m):
    return "%d m" % m if m < 1000 else "%d km" % (m // 1000)


class MapaTrajeto(Widget):
    pontos = ListProperty([])   # [(lat, lon, vel_kmh), ...]
    limite = NumericProperty(32)

    def __init__(self, **kw):
        super().__init__(**kw)
        self._aviso = Label(font_size=tema.T_ROTULO, color=tema.CIANO_FRACO,
                            size_hint=(None, None), size=(dp(200), dp(20)))
        self._lbl_inicio = Label(text="Início", font_size=tema.T_ROTULO, color=tema.CIANO_FRACO,
                                 size_hint=(None, None), size=(dp(44), dp(18)))
        self._lbl_fim = Label(text="Fim", font_size=tema.T_ROTULO, color=tema.CIANO_FRACO,
                              size_hint=(None, None), size=(dp(30), dp(18)))
        self._lbl_regua = Label(font_size=tema.T_ROTULO, color=tema.CIANO_FRACO,
                                size_hint=(None, None), size=(dp(60), dp(18)))
        for w in (self._aviso, self._lbl_inicio, self._lbl_fim, self._lbl_regua):
            self.add_widget(w)
        self.bind(pos=self._d, size=self._d, pontos=self._d, limite=self._d)

    def _d(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*tema.PAINEL)
            Rectangle(pos=self.pos, size=self.size)
        tem_trajeto = len(self.pontos) >= 2
        for lbl in (self._lbl_inicio, self._lbl_fim, self._lbl_regua):
            lbl.opacity = 1 if tem_trajeto else 0
        if not tem_trajeto:
            self._aviso.text = "Sem trajeto gravado"
            self._aviso.center = self.center
            return
        self._aviso.text = ""

        # metros a partir do canto sudoeste
        lat_min = min(p[0] for p in self.pontos)
        lon_min = min(p[1] for p in self.pontos)
        lat_meio = (lat_min + max(p[0] for p in self.pontos)) / 2.0
        kx = M_POR_GRAU_LON * math.cos(math.radians(lat_meio))
        xs = [(p[1] - lon_min) * kx for p in self.pontos]
        ys = [(p[0] - lat_min) * M_POR_GRAU_LAT for p in self.pontos]
        larg_m = max(max(xs), AREA_MINIMA_M)
        alt_m = max(max(ys), AREA_MINIMA_M)

        # área útil: legenda em cima, régua embaixo
        pad = dp(14)
        topo, base = dp(32), dp(24)
        w = self.width - 2 * pad
        h = self.height - 2 * pad - topo - base
        if w <= 0 or h <= 0:
            return
        esc = min(w / larg_m, h / alt_m)  # px por metro, igual nos dois eixos
        ox = self.x + pad + (w - max(xs) * esc) / 2.0
        oy = self.y + pad + base + (h - max(ys) * esc) / 2.0
        tela = [(ox + x * esc, oy + y * esc) for x, y in zip(xs, ys)]

        # trechos seguidos da mesma cor viram uma linha só (emendados)
        trechos = []
        for (px, py), p in zip(tela, self.pontos):
            acima = p[2] > self.limite
            if not trechos or trechos[-1][0] != acima:
                emenda = trechos[-1][1][-2:] if trechos else []
                trechos.append((acima, emenda + [px, py]))
            else:
                trechos[-1][1].extend((px, py))

        (x0, y0), (x1, y1) = tela[0], tela[-1]
        r = dp(5)
        with self.canvas.before:
            for acima, pts in trechos:
                if len(pts) < 4:
                    continue
                cor = tema.LARANJA if acima else tema.CIANO
                Color(*tema.com_alfa(cor, 0.22))
                Line(points=pts, width=dp(3.5), joint="round", cap="round")
                Color(*cor)
                Line(points=pts, width=dp(1.4), joint="round", cap="round")
            # início (verde) e fim (branco)
            Color(*tema.VERDE)
            Ellipse(pos=(x0 - r, y0 - r), size=(2 * r, 2 * r))
            Color(*tema.BRANCO)
            Ellipse(pos=(x1 - r, y1 - r), size=(2 * r, 2 * r))
            Color(*tema.FUNDO)
            Ellipse(pos=(x1 - r / 2, y1 - r / 2), size=(r, r))

            # legenda no canto de cima
            ly = self.top - pad - dp(9)
            Color(*tema.VERDE)
            Ellipse(pos=(self.x + pad, ly - dp(4)), size=(dp(8), dp(8)))
            Color(*tema.BRANCO)
            Ellipse(pos=(self.x + pad + dp(60), ly - dp(4)), size=(dp(8), dp(8)))

            # régua: o maior valor redondo que caiba em ~1/3 da largura
            regua = REGUAS_M[0]
            for m in REGUAS_M:
                if m * esc <= w * 0.35:
                    regua = m
            rx, ry = self.x + pad, self.y + pad + dp(6)
            rw = regua * esc
            Color(*tema.CIANO_FRACO)
            Line(points=[rx, ry + dp(4), rx, ry, rx + rw, ry, rx + rw, ry + dp(4)], width=dp(1))

        self._lbl_inicio.pos = (self.x + pad + dp(10), ly - dp(9))
        self._lbl_fim.pos = (self.x + pad + dp(70), ly - dp(9))
        self._lbl_regua.text = _texto_regua(regua)
        self._lbl_regua.pos = (rx + rw + dp(4), ry - dp(8))
