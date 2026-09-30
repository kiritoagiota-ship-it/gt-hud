"""Suavização da velocidade vinda do GPS.

A velocidade usada é a do próprio GPS (efeito Doppler), que é bem mais
estável que calcular pela diferença entre duas posições. Mesmo assim ela
tem ruído, então passa por uma média móvel exponencial.
"""


class FiltroVelocidade:
    def __init__(self, alfa=0.5, limiar_parado_kmh=2.0, precisao_max_m=20.0):
        self.alfa = alfa
        self.limiar_parado_kmh = limiar_parado_kmh
        self.precisao_max_m = precisao_max_m
        self.reset()

    def reset(self):
        self._valor = 0.0
        self._iniciado = False

    def leitura_valida(self, precisao_m):
        """Descarta posições ruins (ex.: localização por rede, 30 m+)."""
        if precisao_m is None:
            return True
        return precisao_m <= self.precisao_max_m

    def atualizar(self, velocidade_ms):
        kmh = max(0.0, float(velocidade_ms or 0.0) * 3.6)
        if not self._iniciado:
            self._valor = kmh
            self._iniciado = True
        else:
            self._valor = self.alfa * kmh + (1.0 - self.alfa) * self._valor
        return self.valor

    @property
    def valor(self):
        """Velocidade para exibir (km/h). Abaixo do limiar vira 0."""
        if self._valor < self.limiar_parado_kmh:
            return 0.0
        return self._valor
