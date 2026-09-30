"""GPS falso para testar o HUD no PC, sem sair de casa.

Simula uma volta: parado, acelera até ~30 km/h, cruzeiro, passa do limite
(45 km/h) para testar o alerta, freia, para. Com ruído e, de vez em quando,
uma leitura ruim (precisão de 35 m) que o filtro deve descartar.
"""
import math
import random

from kivy.clock import Clock

# Centro de Goiânia
LAT0, LON0 = -16.6799, -49.2550

ROTEIRO = [  # (duração em s, velocidade alvo em km/h)
    (4, 0), (12, 30), (25, 30), (8, 45), (12, 45), (10, 18), (8, 0), (5, 0),
]


class SimuladorGPS:
    def __init__(self, callback):
        self.callback = callback
        self.lat, self.lon = LAT0, LON0
        self.rumo = random.uniform(0, 360)
        self.vel = 0.0
        self._fase = 0
        self._t_fase = 0.0
        self._ev = None

    def iniciar(self):
        if self._ev is None:
            self._ev = Clock.schedule_interval(self._tick, 1.0)

    def parar(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None

    def _tick(self, dt):
        dur, alvo = ROTEIRO[self._fase]
        self._t_fase += dt
        if self._t_fase >= dur:
            self._t_fase = 0.0
            self._fase = (self._fase + 1) % len(ROTEIRO)

        # aceleração de bike elétrica: sobe ~3 km/h/s, freia ~6 km/h/s
        dif = alvo - self.vel
        passo = 3.0 if dif > 0 else 6.0
        self.vel += max(-passo, min(passo, dif))
        self.vel = max(0.0, self.vel)

        self.rumo = (self.rumo + random.uniform(-6, 6)) % 360
        dist = self.vel / 3.6 * dt
        self.lat += dist * math.cos(math.radians(self.rumo)) / 111320.0
        self.lon += dist * math.sin(math.radians(self.rumo)) / (
            111320.0 * math.cos(math.radians(self.lat)))

        ruido = random.gauss(0, 1.2) if self.vel > 0 else 0.0
        precisao = random.uniform(4, 11)
        if random.random() < 0.05:
            precisao = 35.0  # leitura ruim, deve ser descartada

        self.callback(
            lat=self.lat, lon=self.lon,
            speed=max(0.0, (self.vel + ruido) / 3.6),
            bearing=self.rumo, altitude=749.0, accuracy=precisao)
