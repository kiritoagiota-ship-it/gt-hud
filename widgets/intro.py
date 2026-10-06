"""Animação da tela inicial: um "reator" de HUD ligando.

De fora para dentro:
- régua: anel fino com marcas, girando devagar;
- anel de segmentos (como o do velocímetro): um "cometa" de luz dá voltas
  enquanto o GPS procura sinal; quando o sinal chega, todos acendem em
  verde e uma onda se abre para fora;
- três arcos girando no sentido contrário;
- uma linha de varredura que desce pelo disco;
- no centro, o nome do app, que aparece letra por letra.

Custo: tudo é criado uma vez; por quadro só mudam ângulos e cores. Só roda
com a tela inicial à vista (iniciar/parar).
"""
import math

from kivy.clock import Clock
from kivy.graphics import Color, Line, PopMatrix, PushMatrix, Rotate, Scale
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import tema

SEGMENTOS = 48
RASTRO = 16            # segmentos acesos atrás da cabeça do cometa
VOLTA_S = 2.4          # tempo de uma volta do cometa
ENTRADA_S = 0.9        # o anel "abre" ao ligar
LETRA_S = 0.11         # uma letra do nome a cada isso
ONDA_S = 0.75          # onda do "sinal adquirido"
NOME = "GT-HUD"


class AnelBoot(Widget):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._t = 0.0
        self._ev = None
        self._pronto_em = None      # hora (da animação) em que o sinal chegou
        self._segs = []
        self._geo = None
        self.titulo = Label(text="", font_size=dp(44), bold=True, color=tema.CIANO,
                            size_hint=(None, None))
        self.sub = Label(text="Ouxi GT20", font_size=tema.T_ROTULO + 1, color=tema.CIANO_FRACO,
                         size_hint=(None, None), opacity=0)
        self.add_widget(self.titulo)
        self.add_widget(self.sub)
        self.bind(pos=self._montar, size=self._montar)

    # --- controle -------------------------------------------------------------------
    def iniciar(self):
        self._t = 0.0
        self._pronto_em = None
        if self._ev is None:
            self._ev = Clock.schedule_interval(self._passo, 0)

    def parar(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None

    def concluir(self):
        """Sinal adquirido: tudo acende em verde e a onda se abre."""
        if self._pronto_em is None:
            self._pronto_em = self._t

    # --- desenho (uma vez por tamanho) ------------------------------------------------
    def _montar(self, *a):
        r = min(self.width, self.height) / 2.0 - dp(14)
        if r < dp(40):
            return
        cx, cy = self.center_x, self.center_y
        self._geo = (cx, cy, r)
        esp = max(dp(7), r * 0.085)
        passo = 360.0 / SEGMENTOS
        c = self.canvas.before
        c.clear()
        self._segs = []
        with c:
            PushMatrix()
            self._escala = Scale(1, 1, 1, origin=(cx, cy))
            # régua de fora, girando devagar
            PushMatrix()
            self._gira_fora = Rotate(angle=0, origin=(cx, cy))
            self._cor_fora = Color(*tema.com_alfa(tema.CIANO, 0.35))
            Line(circle=(cx, cy, r), width=dp(1))
            for k in range(72):
                a = math.radians(k * 5)
                comp = dp(9) if k % 6 == 0 else dp(4)
                Line(points=[cx + math.sin(a) * (r - comp), cy + math.cos(a) * (r - comp),
                             cx + math.sin(a) * r, cy + math.cos(a) * r], width=dp(1))
            PopMatrix()
            # anel de segmentos
            rs = r - dp(20)
            for i in range(SEGMENTOS):
                a0 = i * passo + passo * 0.14
                cor = Color(*tema.CIANO_APAGADO)
                Line(circle=(cx, cy, rs, a0, a0 + passo * 0.72), width=esp / 2.0, cap="none")
                self._segs.append(cor)
            # três arcos de dentro, no sentido contrário
            PushMatrix()
            self._gira_dentro = Rotate(angle=0, origin=(cx, cy))
            self._cor_dentro = Color(*tema.com_alfa(tema.CIANO, 0.75))
            ri = rs - esp - dp(10)
            for k in range(3):
                Line(circle=(cx, cy, ri, k * 120 + 8, k * 120 + 74), width=dp(1.6), cap="none")
            Color(*tema.com_alfa(tema.CIANO, 0.22))
            Line(circle=(cx, cy, ri - dp(9)), width=dp(1))
            PopMatrix()
            # varredura
            self._cor_varre = Color(*tema.com_alfa(tema.CIANO, 0.0))
            self._varre = Line(points=[cx, cy, cx, cy], width=dp(1.2))
            # onda do sinal adquirido
            self._cor_onda = Color(*tema.com_alfa(tema.VERDE, 0.0))
            self._onda = Line(circle=(cx, cy, r), width=dp(2))
            PopMatrix()
        self._r_dentro = ri - dp(12)
        self.titulo.font_size = min(dp(52), r * 0.36)
        self.titulo.size = (r * 1.6, r * 0.5)
        self.titulo.center = (cx, cy + r * 0.07)
        self.sub.size = (r * 1.6, dp(22))
        self.sub.center = (cx, cy - r * 0.26)
        self._pintar()

    # --- por quadro --------------------------------------------------------------------
    def _passo(self, dt):
        self._t += min(dt, 0.05)
        self._pintar()

    def _pintar(self):
        if self._geo is None or not self._segs:
            return
        t = self._t
        cx, cy, r = self._geo
        # entrada: o anel cresce e aparece
        e = min(1.0, t / ENTRADA_S)
        e = 1 - (1 - e) ** 3
        self._escala.x = self._escala.y = 0.72 + 0.28 * e
        self._gira_fora.angle = -t * 14.0
        self._gira_dentro.angle = t * 46.0
        pronto = self._pronto_em is not None
        desde = t - self._pronto_em if pronto else 0.0
        cor = tema.VERDE if pronto else tema.CIANO
        self._cor_fora.rgba = tema.com_alfa(cor, 0.35 * e)
        self._cor_dentro.rgba = tema.com_alfa(cor, 0.75 * e)
        # cometa: a cabeça dá voltas; atrás dela o brilho vai caindo
        cabeca = (t / VOLTA_S * SEGMENTOS) % SEGMENTOS
        apagado = tema.CIANO_APAGADO
        for i, c in enumerate(self._segs):
            if pronto:
                # acendem todos, a partir da cabeça, em ~0,35 s
                atras = (cabeca - i) % SEGMENTOS
                f = 1.0 if desde * SEGMENTOS / 0.35 >= atras else 0.0
            else:
                atras = (cabeca - i) % SEGMENTOS
                f = max(0.0, 1.0 - atras / RASTRO) ** 1.6 if atras < RASTRO else 0.0
            c.rgba = (apagado[0] + (cor[0] - apagado[0]) * f, apagado[1] + (cor[1] - apagado[1]) * f,
                      apagado[2] + (cor[2] - apagado[2]) * f, e)
        # varredura: desce pelo disco de dentro, clareando no meio do caminho
        f = (t % 2.6) / 2.6
        y = cy + self._r_dentro * (1 - 2 * f)
        meia = math.sqrt(max(0.0, self._r_dentro ** 2 - (y - cy) ** 2))
        self._varre.points = [cx - meia, y, cx + meia, y]
        self._cor_varre.rgba = tema.com_alfa(cor, 0.30 * math.sin(math.pi * f) * e)
        # onda
        if pronto and desde < ONDA_S:
            g = desde / ONDA_S
            self._onda.circle = (cx, cy, r * (1.0 + 0.32 * g))
            self._cor_onda.rgba = tema.com_alfa(tema.VERDE, 0.8 * (1 - g))
        else:
            self._cor_onda.rgba = (0, 0, 0, 0)
        # nome, letra por letra (com um cursor enquanto escreve)
        letras = int(max(0.0, t - 0.35) / LETRA_S)
        if letras >= len(NOME):
            texto = NOME
            self.sub.opacity = min(1.0, (t - 0.35 - len(NOME) * LETRA_S) / 0.4)
        else:
            texto = NOME[:letras] + "_"
            self.sub.opacity = 0
        if self.titulo.text != texto:
            self.titulo.text = texto
        self.titulo.color = cor
