"""Perfil de altimetria da rota: a "silhueta" das subidas e descidas, com as
subidas que merecem aviso pintadas de laranja."""
from kivy.graphics import Color, Line, Mesh
from kivy.metrics import dp
from kivy.properties import ListProperty, NumericProperty
from kivy.uix.widget import Widget

import tema


class PerfilAltimetria(Widget):
    elevacao = ListProperty([])   # altitude a cada `passo` metros
    subidas = ListProperty([])    # [{inicio_m, fim_m, ...}] (rota.achar_subidas)
    passo = NumericProperty(30)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self._d, size=self._d, elevacao=self._d, subidas=self._d)

    def _d(self, *a):
        self.canvas.clear()
        e = self.elevacao
        if len(e) < 2 or self.width < 10:
            return
        baixo, alto = min(e), max(e)
        faixa = max(alto - baixo, 15.0)  # rota plana não vira montanha-russa
        pad = dp(2)
        w, h = self.width - 2 * pad, self.height - 2 * pad

        def ponto(i):
            return (self.x + pad + w * i / (len(e) - 1),
                    self.y + pad + h * 0.08 + h * 0.84 * (e[i] - baixo) / faixa)

        pts = [ponto(i) for i in range(len(e))]
        vert, ind = [], []
        for n, (x, y) in enumerate(pts):
            vert += [x, self.y + pad, 0, 0, x, y, 0, 0]
            if n:
                b = 2 * n
                ind += [b - 2, b - 1, b, b - 1, b + 1, b]
        with self.canvas:
            Color(*tema.com_alfa(tema.CIANO, 0.14))
            Mesh(vertices=vert, indices=ind, mode="triangles")
            Color(*tema.CIANO)
            Line(points=[c for p in pts for c in p], width=dp(1.3))
            Color(*tema.LARANJA)
            for s in self.subidas:
                i0 = int(s["inicio_m"] / self.passo)
                i1 = min(len(e) - 1, int(s["fim_m"] / self.passo))
                if i1 > i0:
                    Line(points=[c for p in pts[i0:i1 + 1] for c in p], width=dp(2.2))
