"""Velocímetro circular segmentado.

Arco de 270 graus dividido em segmentos. Os segmentos acima do limite
configurado ficam em laranja; ao passar do limite, o número e o anel piscam.
"""
import math

from kivy.clock import Clock
from kivy.graphics import Color, Line
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import tema

# No Kivy, 0 grau é o topo e o ângulo cresce no sentido horário.
INICIO, FIM = -135.0, 135.0


class Velocimetro(Widget):
    velocidade = NumericProperty(0)
    maximo = NumericProperty(60)
    limite = NumericProperty(32)
    alerta = BooleanProperty(False)
    segmentos = 30

    def __init__(self, **kw):
        super().__init__(**kw)
        self._piscar_on = True
        self._ev_piscar = None
        self.lbl_valor = Label(text="0", bold=True, color=tema.BRANCO,
                               size_hint=(None, None))
        self.lbl_unidade = Label(text="km/h", color=tema.CIANO_FRACO,
                                 size_hint=(None, None))
        self.marcas = [Label(text=str(v), color=tema.CIANO_FRACO, size_hint=(None, None),
                             size=(dp(30), dp(20))) for v in range(0, 61, 10)]
        for w in [self.lbl_valor, self.lbl_unidade] + self.marcas:
            self.add_widget(w)
        self._gatilho = Clock.create_trigger(self._desenhar, 0)
        self.bind(pos=self._gatilho, size=self._gatilho, limite=self._gatilho,
                  maximo=self._gatilho, velocidade=self._on_velocidade,
                  alerta=self._on_alerta)

    # ------------------------------------------------------------------
    @staticmethod
    def _polar(cx, cy, raio, angulo):
        a = math.radians(angulo)
        return cx + math.sin(a) * raio, cy + math.cos(a) * raio

    def _angulo(self, v):
        frac = max(0.0, min(1.0, v / float(self.maximo)))
        return INICIO + (FIM - INICIO) * frac

    def _on_velocidade(self, *a):
        self.lbl_valor.text = "%d" % round(self.velocidade)
        self._gatilho()

    def _on_alerta(self, *a):
        if self.alerta and self._ev_piscar is None:
            self._ev_piscar = Clock.schedule_interval(self._piscar, 0.35)
        elif not self.alerta and self._ev_piscar is not None:
            self._ev_piscar.cancel()
            self._ev_piscar = None
            self._piscar_on = True
        self._gatilho()

    def _piscar(self, dt):
        self._piscar_on = not self._piscar_on
        self._gatilho()

    # ------------------------------------------------------------------
    def _desenhar(self, *a):
        # o anel ocupa 270 graus: sobra espaco embaixo, entao o centro desce
        # um pouco para o desenho ficar equilibrado na area disponivel
        r = min(self.width / 2.0 - dp(10), self.height / 1.9 - dp(6))
        cx = self.x + self.width / 2.0
        cy = self.y + self.height / 2.0 - r * 0.12
        if r <= dp(20):
            return
        esp = max(dp(8), r * 0.12)
        passo = (FIM - INICIO) / self.segmentos
        folga = passo * 0.25
        acesos = self.velocidade / float(self.maximo) * self.segmentos
        apagado_pisca = self.alerta and not self._piscar_on

        cb = self.canvas.before
        cb.clear()
        with cb:
            # anel interno fino
            Color(*tema.com_alfa(tema.CIANO, 0.22))
            Line(circle=(cx, cy, r - esp * 1.25, INICIO, FIM), width=dp(1))

            for i in range(self.segmentos):
                a0 = INICIO + i * passo + folga / 2.0
                a1 = a0 + passo - folga
                v_seg = (i + 0.5) * self.maximo / float(self.segmentos)
                acima = v_seg > self.limite
                if i < acesos:
                    cor = tema.LARANJA if acima else tema.CIANO
                    if apagado_pisca:
                        cor = tema.com_alfa(cor, 0.3)
                    Color(*tema.com_alfa(cor, 0.16))
                    Line(circle=(cx, cy, r, a0, a1), width=esp * 0.85, cap="none")
                    Color(*cor)
                else:
                    Color(*(tema.com_alfa(tema.LARANJA, 0.2) if acima else tema.CIANO_APAGADO))
                Line(circle=(cx, cy, r, a0, a1), width=esp / 2.0, cap="none")

            # marca do limite, por fora do anel
            al = self._angulo(self.limite)
            p1 = self._polar(cx, cy, r + esp * 0.6, al)
            p2 = self._polar(cx, cy, r + esp * 1.3, al)
            Color(*tema.LARANJA)
            Line(points=[p1[0], p1[1], p2[0], p2[1]], width=dp(2))

        # textos
        self.lbl_valor.font_size = r * 0.62
        self.lbl_valor.size = (r * 1.4, r * 0.7)
        self.lbl_valor.center = (cx, cy + r * 0.06)
        cor_num = tema.LARANJA if self.alerta else tema.BRANCO
        if apagado_pisca:
            cor_num = tema.com_alfa(cor_num, 0.35)
        self.lbl_valor.color = cor_num

        self.lbl_unidade.font_size = max(dp(12), r * 0.13)
        self.lbl_unidade.size = (r, r * 0.2)
        self.lbl_unidade.center = (cx, cy - r * 0.42)

        for lbl, v in zip(self.marcas, range(0, 61, 10)):
            lbl.font_size = max(dp(10), r * 0.085)
            lbl.center = self._polar(cx, cy, r - esp * 2.1, self._angulo(v))
