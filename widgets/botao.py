"""Botão com cantos cortados (estilo HUD)."""
from kivy.graphics import Color, Line, Mesh
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty
from kivy.uix.button import Button

import tema


def _poligono(x, y, w, h, c):
    # corta o canto superior esquerdo e o inferior direito
    return [(x + c, y + h), (x + w, y + h), (x + w, y + c),
            (x + w - c, y), (x, y), (x, y + h - c)]


class BotaoHUD(Button):
    destaque = BooleanProperty(False)
    cor = ListProperty(tema.CIANO)
    opaco = BooleanProperty(False)  # por cima do mapa: fundo escuro, senão some na rua clara

    def __init__(self, **kw):
        kw.setdefault("font_size", tema.T_BOTAO)
        kw.setdefault("bold", True)
        super().__init__(**kw)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.bind(pos=self._desenhar, size=self._desenhar, state=self._desenhar,
                  destaque=self._desenhar, cor=self._desenhar, opaco=self._desenhar)
        self._desenhar()

    def _desenhar(self, *a):
        c = min(dp(12), self.height * 0.3)
        pts = _poligono(self.x, self.y, self.width, self.height, c)
        plano = [v for p in pts for v in p]
        self.canvas.before.clear()
        with self.canvas.before:
            pressionado = self.state == "down"
            if self.opaco and not self.destaque:
                Color(*tema.com_alfa(tema.PAINEL, 0.94))
                vert = []
                for px, py in pts:
                    vert += [px, py, 0, 0]
                Mesh(vertices=vert, indices=list(range(len(pts))), mode="triangle_fan")
            if self.destaque or pressionado:
                alfa = 1.0 if self.destaque else 0.25
                if self.destaque and pressionado:
                    alfa = 0.7
                Color(*tema.com_alfa(self.cor, alfa))
                vert = []
                for px, py in pts:
                    vert += [px, py, 0, 0]
                Mesh(vertices=vert, indices=list(range(len(pts))), mode="triangle_fan")
            Color(*self.cor)
            Line(points=plano, close=True, width=dp(1.2))
        self.color = tema.FUNDO if self.destaque else self.cor
