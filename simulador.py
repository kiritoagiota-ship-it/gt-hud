"""GPS falso para testar o HUD no PC, sem sair de casa.

Simula uma volta: parado, acelera até ~30 km/h, cruzeiro, passa do limite
(45 km/h) para testar o alerta, freia, para. Com ruído e, de vez em quando,
uma leitura ruim (precisão de 35 m) que o filtro deve descartar.

Com uma rota (seguir_rota), anda POR ELA no mesmo ritmo, com as paradas do
roteiro fazendo papel de semáforo: dá para testar a navegação inteira em
casa. desvio_m tira o "ciclista" da rota (para testar o recálculo).
"""
import math
import random

from kivy.clock import Clock

from rota import distancia_m

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
        self._rota = None
        self._acumulado = []
        self._d = 0.0
        self.desvio_m = 0.0

    def seguir_rota(self, pontos):
        if len(pontos) < 2:
            return
        self._rota = list(pontos)
        self._acumulado = [0.0]
        for a, b in zip(pontos, pontos[1:]):
            self._acumulado.append(self._acumulado[-1] + distancia_m(a, b))
        self._d = 0.0
        self.lat, self.lon = pontos[0]

    def deixar_rota(self):
        self._rota = None

    def _andar_na_rota(self, dist):
        self._d = min(self._d + dist, self._acumulado[-1])
        i = 0
        while i < len(self._acumulado) - 2 and self._acumulado[i + 1] < self._d:
            i += 1
        a, b = self._rota[i], self._rota[i + 1]
        comp = self._acumulado[i + 1] - self._acumulado[i]
        f = (self._d - self._acumulado[i]) / comp if comp else 0.0
        if comp:
            self.rumo = math.degrees(math.atan2((b[1] - a[1]) * math.cos(math.radians(a[0])),
                                                b[0] - a[0])) % 360
        # desvio para o LADO da rota (perpendicular ao rumo)
        lado = math.radians(self.rumo + 90)
        self.lat = a[0] + (b[0] - a[0]) * f + self.desvio_m * math.cos(lado) / 110540.0
        self.lon = a[1] + (b[1] - a[1]) * f + self.desvio_m * math.sin(lado) / (
            111320.0 * math.cos(math.radians(a[0])))

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

        dist = self.vel / 3.6 * dt
        if self._rota:
            if self._d >= self._acumulado[-1]:
                self.vel = 0.0  # chegou no fim da rota: fica parado
            self._andar_na_rota(dist)
        else:
            self.rumo = (self.rumo + random.uniform(-6, 6)) % 360
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
            bearing=self.rumo if self.vel > 0 else None, altitude=749.0, accuracy=precisao)
