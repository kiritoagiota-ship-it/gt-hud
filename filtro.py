"""Velocidade do velocímetro a partir do GPS.

A velocidade usada é a do próprio GPS (efeito Doppler), bem mais estável
que calcular pela diferença entre duas posições. Ela tem dois defeitos:
ruído (o número treme) e ATRASO (o GPS entrega 1 leitura por segundo, que
já é a média do segundo que passou).

Até a versão 1.0.19 isso passava por uma média móvel simples: para o número
não tremer, ele ficava 1 a 2 s atrasado em toda acelerada e freada (o dono
achou o velocímetro pouco preciso). Agora é um filtro de Kalman com dois
estados, velocidade e aceleração.

Calibração de 07/10/2026 (o dono: "atrasa" e "diferente do painel da moto"),
medida numa simulação com arrancada de 1,2 m/s2 e freada de 2 m/s2: o atraso
do número caiu de ~1,4 s para ~0,8 s, e ao parar de 1,4 s para 0,6 s. Como:
- a leitura do GPS é tratada como o que ela é: a MÉDIA do último intervalo
  (meio intervalo atrás), e ainda chega com `idade` de atraso do chip;
- ARRANCADA: saindo do zero, o filtro recomeça na hora (antes "duvidava");
- previsto(): entre uma leitura e outra (1 por segundo) o número continua
  andando pela tendência, em vez de esperar a próxima;
- `ajuste`: fator para igualar ao painel da moto, se a pessoa quiser.
O que sobra de atraso é do próprio GPS (1 leitura por segundo).

O filtro:
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
ADIANTO_MAX_MS = 3.0         # o adianto nunca passa disso (uns 6 km/h)
IDADE_PADRAO_S = 0.35        # atraso típico do chip do GPS para entregar a leitura
IDADE_MAX_S = 1.2
ACEL_FOLGA = 0.2            # m/s2; abaixo disso a tendência não é usada para adiantar
CALMO_S = 3.0                # a "média calma" olha mais ou menos esse tempo para trás
CALMO_FOLGA_KMH = 0.7        # até isso de diferença para a média calma: mostra a média
CALMO_FAIXA_KMH = 1.6        # ... e daí até folga+faixa vai passando para o valor rápido
PREVER_MAX_S = 1.2           # sem leitura nova por isso: para de prever
BURACO_S = 3.5               # sem leitura por mais que isso: recomeça da leitura nova
MEMORIA_ACEL_S = 4.0         # a aceleração estimada "esquece" nesse tempo
PARADO_MS = 0.35             # 2 leituras seguidas abaixo disso: parado de vez
Q_BASE = 0.25                 # ruído de processo (o quanto a aceleração muda), na resposta 0,5


class FiltroVelocidade:
    def __init__(self, alfa=0.5, limiar_parado_kmh=2.0, precisao_max_m=20.0):
        self.alfa = alfa   # "Resposta do velocímetro" dos Ajustes (0,1 a 0,9)
        # "Ajuste do velocímetro" dos Ajustes: multiplica o que é mostrado (1,00 =
        # a velocidade real do GPS; o painel da moto costuma marcar uns 5-10% a mais)
        self.ajuste = 1.0
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
        self._calmo = 0.0      # km/h: média calma dos últimos segundos
        self._chegou = 0.0     # relógio em que a última leitura chegou
        self._idade = IDADE_PADRAO_S

    def leitura_valida(self, precisao_m):
        """Descarta posições ruins (ex.: localização por rede, 30 m+)."""
        if precisao_m is None:
            return True
        return precisao_m <= self.precisao_max_m

    def atualizar(self, velocidade_ms, t=None, incerteza_ms=None, idade_s=None, agora=None):
        """velocidade_ms: a do GPS; t: hora da leitura (s, relógio que só
        anda para a frente); incerteza_ms: a que o GPS informou, se informou;
        idade_s: há quanto tempo a leitura foi feita quando chegou ao app
        (o chip do GPS demora para entregar); agora: relógio de previsto()."""
        z = max(0.0, float(velocidade_ms or 0.0))
        self._chegou = time.monotonic() if agora is None else float(agora)
        self._idade = IDADE_PADRAO_S if idade_s is None else max(0.0, min(IDADE_MAX_S, float(idade_s)))
        t = time.monotonic() if t is None else float(t)
        dt = None if self._t is None else t - self._t
        if dt is not None and dt <= 0.02:
            return self.valor  # leitura repetida (mesma hora): nada novo
        self._t = t
        if not self._iniciado or dt > BURACO_S:
            self._v, self._a, self._p = z, 0.0, [1.0, 0.0, 1.0]
            self._calmo = z * 3.6
            self._iniciado = True
            self._parado = 0
            self._valor = z * 3.6 * self.ajuste
            return self.valor

        if self._parado >= 2 and z >= PARADO_MS:
            # ARRANCADA: estava parado e a leitura mostra movimento. O filtro
            # "parado" (velocidade 0, sem tendência) demorava vários segundos
            # para acreditar: recomeça já na leitura, com a aceleração que ela indica.
            self._parado = 0
            self._v, self._a = z, max(0.0, min(ACEL_MAX, z / max(dt, 0.2)))
            self._p = [0.5, 0.0, 2.0]
            self._calmo = z * 3.6
            self._valor = self._com_adianto(0.0)
            return self.valor

        # 1) previsão: a velocidade seguiu a tendência desde a última leitura
        v, a = self._v, self._a
        pvv, pva, paa = self._p
        # "Resposta" dos Ajustes: maior = segura a tendência por mais tempo (acompanha
        # mais rápido, mas passa um pouco do ponto ao fim da acelerada); menor = mais calmo
        esquecer = math.exp(-dt / (MEMORIA_ACEL_S * (0.5 + self.alfa)))
        v += a * dt
        a *= esquecer
        q = Q_BASE * (0.4 + 1.2 * self.alfa) ** 2   # o quanto a aceleração pode mudar
        pvv = pvv + 2 * dt * pva + dt * dt * paa + q * dt ** 3 / 3.0
        pva = (pva + dt * paa) * esquecer + q * dt * dt / 2.0
        paa = paa * esquecer * esquecer + q * dt

        # 2) correção pela leitura, pesada pela confiança nela
        r = min(INCERTEZA_MAX_MS, max(INCERTEZA_MIN_MS, incerteza_ms or INCERTEZA_PADRAO_MS))
        # O que o GPS entrega é a MÉDIA da velocidade no intervalo que passou,
        # ou seja, a velocidade de meio intervalo atrás: z = v - h*a. Dizer isso
        # ao filtro (em vez de somar um "adianto" por fora) faz ele achar a
        # velocidade de AGORA e perceber a aceleração uma leitura mais cedo.
        h = min(dt, 1.5) / 2.0
        erro = z - (v - h * a)
        if abs(erro) > ACEL_MAX * dt + 3.0 * r:
            r *= 12.0  # pulo que uma bicicleta não dá: quase não conta
        hv, ha = pvv - h * pva, pva - h * paa          # H.P
        s = hv - h * ha + r * r                        # H.P.Ht + R
        kv, ka = hv / s, ha / s
        v += kv * erro
        a += ka * erro
        self._p = [pvv - kv * hv, pva - kv * ha, paa - ka * ha]
        a = max(-ACEL_MAX, min(ACEL_MAX, a))

        # 3) parado é parado: não fica "descendo devagar" até o zero
        self._parado = self._parado + 1 if z < PARADO_MS else 0
        if self._parado >= 2:
            v, a = 0.0, 0.0
            self._calmo = 0.0
        self._v, self._a = max(0.0, v), a
        self._calmo += (self._v * 3.6 - self._calmo) * min(1.0, dt / CALMO_S)

        # o adianto só entra na medida em que a aceleração é de verdade (e não
        # ruído): em ritmo constante ele some e o número não treme
        self._valor = self._com_adianto(0.0)
        return self.valor

    def _com_adianto(self, depois_s):
        """km/h estimados para `depois_s` segundos DEPOIS de a leitura chegar.
        A leitura já chega velha (levou `idade` para ser entregue): soma-se a
        tendência (aceleração) por esse tempo, com a confiança que se tem nela."""
        certeza = self._a * self._a / (self._a * self._a + max(0.0, self._p[2]) + 1e-9)
        tempo = self._idade + depois_s
        # aceleração pequena é quase sempre ruído: só a parte que passa de
        # ACEL_FOLGA entra (em ritmo constante o número fica quieto)
        acel = math.copysign(max(0.0, abs(self._a) - ACEL_FOLGA), self._a)
        adianto = max(-ADIANTO_MAX_MS, min(ADIANTO_MAX_MS, acel * tempo * certeza))
        rapido = max(0.0, self._v + adianto) * 3.6
        # Ritmo constante: o valor rápido ainda balança 1 ou 2 km/h com o ruído
        # do GPS. Perto da média calma dos últimos segundos, mostra a média; ao
        # se afastar dela (acelerou/freou de verdade), passa para o rápido.
        longe = abs(rapido - self._calmo)
        peso = max(0.0, min(1.0, (longe - CALMO_FOLGA_KMH) / CALMO_FAIXA_KMH))
        return (self._calmo + (rapido - self._calmo) * peso) * self.ajuste

    def previsto(self, agora=None):
        """Velocidade para exibir AGORA, entre uma leitura e outra do GPS
        (ele dá 1 por segundo): numa acelerada o número segue subindo em vez
        de esperar a próxima leitura. Sem leitura há mais de PREVER_MAX_S,
        para de prever."""
        if not self._iniciado or self._parado >= 2:
            return self.valor
        agora = time.monotonic() if agora is None else float(agora)
        depois = max(0.0, min(PREVER_MAX_S, agora - self._chegou))
        kmh = self._com_adianto(depois)
        return 0.0 if kmh < self.limiar_parado_kmh else kmh

    @property
    def valor(self):
        """Velocidade para exibir (km/h). Abaixo do limiar vira 0."""
        if self._valor < self.limiar_parado_kmh:
            return 0.0
        return self._valor
