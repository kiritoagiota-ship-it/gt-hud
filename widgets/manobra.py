"""Ícone da manobra (seta desenhada à mão, no traço do HUD).

As fontes do app não têm setas (e emoji não renderiza), então cada ícone é
um caminho de pontos num quadrado 0..1 com a ponta de seta no fim.
"""
import math

from kivy.graphics import Color, Line, Triangle
from kivy.metrics import dp
from kivy.properties import NumericProperty, StringProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import tema

# caminho de cada ação (x, y de 0 a 1, y para cima); a seta sai do último ponto
_RETO = [(0.5, 0.08), (0.5, 0.92)]
_CAMINHOS = {
    "em_frente": _RETO,
    "esquerda": [(0.62, 0.08), (0.62, 0.52), (0.14, 0.52)],
    "direita": [(0.38, 0.08), (0.38, 0.52), (0.86, 0.52)],
    "levemente_esquerda": [(0.6, 0.08), (0.6, 0.45), (0.22, 0.86)],
    "levemente_direita": [(0.4, 0.08), (0.4, 0.45), (0.78, 0.86)],
    "acentuada_esquerda": [(0.66, 0.08), (0.66, 0.72), (0.2, 0.28)],
    "acentuada_direita": [(0.34, 0.08), (0.34, 0.72), (0.8, 0.28)],
    "retorno": [(0.66, 0.08), (0.66, 0.66), (0.62, 0.8), (0.5, 0.86), (0.38, 0.8),
                (0.34, 0.66), (0.34, 0.36)],
    "mantenha_esquerda": [(0.6, 0.08), (0.6, 0.4), (0.3, 0.7), (0.3, 0.92)],
    "mantenha_direita": [(0.4, 0.08), (0.4, 0.4), (0.7, 0.7), (0.7, 0.92)],
}
_CAMINHOS["saida_esquerda"] = _CAMINHOS["levemente_esquerda"]
_CAMINHOS["saida_direita"] = _CAMINHOS["levemente_direita"]
_CAMINHOS["sair_rotatoria"] = _CAMINHOS["levemente_direita"]


class IconeManobra(Widget):
    acao = StringProperty("em_frente")
    saida = NumericProperty(0)  # rotatória: número da saída

    def __init__(self, **kw):
        super().__init__(**kw)
        self._num = Label(bold=True, color=tema.BRANCO)
        self.add_widget(self._num)
        self.bind(pos=self._d, size=self._d, acao=self._d, saida=self._d)

    def _p(self, x, y):
        lado = min(self.width, self.height)
        ox = self.center_x - lado / 2
        oy = self.center_y - lado / 2
        return ox + x * lado, oy + y * lado

    def _d(self, *a):
        # canvas.before: limpar o canvas principal apagaria o número (o Label
        # filho desenha dentro dele)
        self.canvas.before.clear()
        lado = min(self.width, self.height)
        grossura = max(dp(3), lado * 0.075)
        self._num.text = ""
        with self.canvas.before:
            Color(*tema.CIANO)
            if self.acao.startswith("chegada"):
                # alvo: o destino
                cx, cy = self._p(0.5, 0.5)
                for r, g in ((0.40, 0.06), (0.24, 0.06)):
                    Line(circle=(cx, cy, lado * r), width=lado * g / 2)
                Line(circle=(cx, cy, lado * 0.06), width=lado * 0.06)
                return
            if self.acao == "rotatoria":
                cx, cy = self._p(0.5, 0.52)
                Line(circle=(cx, cy, lado * 0.22), width=grossura / 2)
                Line(points=[*self._p(0.5, 0.06), *self._p(0.5, 0.3)], width=grossura / 2)
                caminho = [(0.66, 0.66), (0.86, 0.86)]
                self._num.text = str(self.saida) if self.saida else ""
                self._num.font_size = lado * 0.26
                self._num.size = (lado * 0.4, lado * 0.4)
                self._num.center = (cx, cy)
            else:
                caminho = _CAMINHOS.get(self.acao, _RETO)
            pts = [c for p in caminho for c in self._p(*p)]
            Line(points=pts, width=grossura / 2, joint="round", cap="round")
            # ponta da seta na direção do último trecho
            (x0, y0), (x1, y1) = self._p(*caminho[-2]), self._p(*caminho[-1])
            ang = math.atan2(y1 - y0, x1 - x0)
            tam = lado * 0.2
            ponta = (x1 + math.cos(ang) * tam * 0.35, y1 + math.sin(ang) * tam * 0.35)
            esq = (x1 + math.cos(ang + 2.5) * tam, y1 + math.sin(ang + 2.5) * tam)
            dir_ = (x1 + math.cos(ang - 2.5) * tam, y1 + math.sin(ang - 2.5) * tam)
            Triangle(points=[*ponta, *esq, *dir_])
