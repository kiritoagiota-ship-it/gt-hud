"""Gráfico simples de velocidade ao longo da viagem."""
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.properties import ListProperty, NumericProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import tema


class GraficoVelocidade(Widget):
    pontos = ListProperty([])   # [(t, vel_kmh), ...]
    limite = NumericProperty(32)

    def __init__(self, **kw):
        super().__init__(**kw)
        self._lbl = Label(font_size=tema.T_ROTULO, color=tema.CIANO_FRACO,
                          size_hint=(None, None), size=(dp(160), dp(20)))
        self.add_widget(self._lbl)
        self.bind(pos=self._d, size=self._d, pontos=self._d, limite=self._d)

    def _d(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*tema.PAINEL)
            Rectangle(pos=self.pos, size=self.size)
        if len(self.pontos) < 2:
            self._lbl.text = "Sem dados de velocidade"
            self._lbl.center = (self.x + self.width / 2, self.y + self.height / 2)
            return
        pad = dp(10)
        x0, y0 = self.x + pad, self.y + pad
        w, h = self.width - 2 * pad, self.height - 2 * pad - dp(18)
        t0, t1 = self.pontos[0][0], self.pontos[-1][0]
        pico = max(v for _, v in self.pontos)
        vmax = max(pico, self.limite, 10) * 1.1
        dur = max(t1 - t0, 1)
        passo = max(1, int(len(self.pontos) / max(w, 1)))  # até 1 ponto por pixel
        pts = []
        for t, v in self.pontos[::passo]:
            pts += [x0 + (t - t0) / dur * w, y0 + v / vmax * h]
        y_lim = y0 + self.limite / vmax * h
        with self.canvas.before:
            Color(*tema.com_alfa(tema.LARANJA, 0.7))
            Line(points=[x0, y_lim, x0 + w, y_lim], width=1, dash_length=6, dash_offset=4)
            Color(*tema.com_alfa(tema.CIANO, 0.2))
            Line(points=pts, width=dp(3))
            Color(*tema.CIANO)
            Line(points=pts, width=dp(1.2))
        self._lbl.text = "Pico %.0f km/h" % pico
        self._lbl.center = (self.x + self.width - dp(80), self.y + self.height - dp(14))
