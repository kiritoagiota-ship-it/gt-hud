"""Velocidade do velocímetro a partir do GPS.

A velocidade usada é a do próprio GPS (efeito Doppler), bem mais estável
que calcular pela diferença entre duas posições. Ela tem dois defeitos:
ruído (o número treme) e ATRASO (o GPS entrega 1 leitura por segundo, que
já é a média do segundo que passou).

Até a versão 1.0.19 isso passava por uma média móvel simples: para o número
não tremer, ele ficava 1 a 2 s atrasado em toda acelerada e freada (o dono
achou o velocímetro pouco preciso). Agora é um filtro de Kalman com dois
estados, velocidade e aceleração:
- parado ou em ritmo constante, o número fica firme (o ruído é filtrado);
- acelerando ou freando, o filtro percebe a tendência e acompanha, e ainda
  adianta a leitura em ADIANTO_S para compensar o atraso do GPS;
- usa a incerteza que o próprio GPS informa para cada leitura (Android 8+):
  leitura boa pesa mais, leitura ruim (prédio, árvore) pesa menos;
- um pulo impossível para uma bicicleta (ACEL_MAX) quase não é ouvido;
- usa a hora exata de cada leitura (o intervalo nem sempre é 1 s).
"""
import math
import time

INCERTEZA_PADRAO_MS = 0.35   # m/s; quando o GPS não informa (ou no simulador)
INCERTEZA_MIN_MS = 0.12      # alguns aparelhos informam um valor otimista demais
INCERTEZA_MAX_MS = 3.0
ACEL_MAX = 7.0               # m/s2; bicicleta freando forte fica abaixo disso
ADIANTO_S = 0.45             # o Doppler é a média do último intervalo: meio intervalo atrasado
ADIANTO_MAX_MS = 0.9         # o adianto nunca passa disso (uns 3 km/h)
BURACO_S = 3.5               # sem leitura por mais que isso: recomeça da leitura nova
MEMORIA_ACEL_S = 5.0         # a aceleração estimada "esquece" nesse tempo
PARADO_MS = 0.35             # 2 leituras seguidas abaixo disso: parado de vez
Q_BASE = 0.1                 # ruído de processo (o quanto a aceleração muda), na resposta 0,5


class FiltroVelocidade:
    def __init__(self, alfa=0.5, limiar_parado_kmh=2.0, precisao_max_m=20.0):
        self.alfa = alfa   # "Resposta do velocímetro" dos Ajustes (0,1 a 0,9)
        self.limiar_parado_kmh = limiar_parado_kmh
        self.precisao_max_m = precisao_max_m
        self.reset()

    def reset(self):
        self._v = 0.0          # m/s
        self._a = 0.0          # m/s2
        self._p = [1.0, 0.0, 1.0]   # covariância: vv, va, aa
        self._t = None
        self._parado = 0
        self._valor = 0.0      # km/h, já com o adianto
        self._iniciado = False

    def leitura_valida(self, precisao_m):
        """Descarta posições ruins (ex.: localização por rede, 30 m+)."""
        if precisao_m is None:
            return True
        return precisao_m <= self.precisao_max_m

    def atualizar(self, velocidade_ms, t=None, incerteza_ms=None):
        """velocidade_ms: a do GPS; t: hora da leitura (s, relógio que só
        anda para a frente); incerteza_ms: a que o GPS informou, se informou."""
        z = max(0.0, float(velocidade_ms or 0.0))
        t = time.monotonic() if t is None else float(t)
        dt = None if self._t is None else t - self._t
        if dt is not None and dt <= 0.02:
            return self.valor  # leitura repetida (mesma hora): nada novo
        self._t = t
        if not self._iniciado or dt > BURACO_S:
            self._v, self._a, self._p = z, 0.0, [1.0, 0.0, 1.0]
            self._iniciado = True
            self._parado = 0
            self._valor = z * 3.6
            return self.valor

        # 1) previsão: a velocidade seguiu a tendência desde a última leitura
        v, a = self._v, self._a
        pvv, pva, paa = self._p
        esquecer = math.exp(-dt / MEMORIA_ACEL_S)
        v += a * dt
        a *= esquecer
        q = Q_BASE * (0.4 + 1.2 * self.alfa) ** 2   # o quanto a aceleração pode mudar
        pvv = pvv + 2 * dt * pva + dt * dt * paa + q * dt ** 3 / 3.0
        pva = (pva + dt * paa) * esquecer + q * dt * dt / 2.0
        paa = paa * esquecer * esquecer + q * dt

        # 2) correção pela leitura, pesada pela confiança nela
        r = min(INCERTEZA_MAX_MS, max(INCERTEZA_MIN_MS, incerteza_ms or INCERTEZA_PADRAO_MS))
        erro = z - v
        if abs(erro) > ACEL_MAX * dt + 3.0 * r:
            r *= 12.0  # pulo que uma bicicleta não dá: quase não conta
        s = pvv + r * r
        kv, ka = pvv / s, pva / s
        v += kv * erro
        a += ka * erro
        self._p = [(1 - kv) * pvv, (1 - kv) * pva, paa - ka * pva]
        a = max(-ACEL_MAX, min(ACEL_MAX, a))

        # 3) parado é parado: não fica "descendo devagar" até o zero
        self._parado = self._parado + 1 if z < PARADO_MS else 0
        if self._parado >= 2:
            v, a = 0.0, 0.0
        self._v, self._a = max(0.0, v), a

        # o adianto só entra na medida em que a aceleração é de verdade (e não
        # ruído): em ritmo constante ele some e o número não treme
        certeza = self._a * self._a / (self._a * self._a + max(0.0, self._p[2]) + 1e-9)
        adianto = max(-ADIANTO_MAX_MS, min(ADIANTO_MAX_MS, self._a * ADIANTO_S * certeza))
        self._valor = max(0.0, self._v + adianto) * 3.6
        return self.valor

    @property
    def valor(self):
        """Velocidade para exibir (km/h). Abaixo do limiar vira 0."""
        if self._valor < self.limiar_parado_kmh:
            return 0.0
        return self._valor
