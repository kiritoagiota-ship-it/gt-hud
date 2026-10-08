"""Tempo de chegada pelo ritmo de quem pedala.

O servidor de rotas calcula o tempo para uma bicicleta "padrão". O dono
anda numa elétrica, no trânsito de Goiânia, do jeito dele: o app compara o
tempo que ele REALMENTE leva com o que o servidor previa para o mesmo
trecho e guarda a proporção (o "fator"): 0,80 = ele chega em 80% do tempo
previsto. Todo tempo de rota mostrado ou falado sai multiplicado por ele
(rota.fator_ritmo).

- Só conta o trecho andado em cima da rota (fora dela não há previsão).
- Parada de até PARADA_CONTA_S conta (semáforo faz parte da viagem); o que
  passar disso não conta (parou para conversar, abastecer...).
- Durante a viagem o fator já vai se ajustando ao ritmo de hoje; no fim, o
  aprendido muda um pouco (viagem longa pesa mais que viagem curta).
"""
import rota as rotas

FATOR_MIN, FATOR_MAX = 0.5, 2.0
PARADA_CONTA_S = 40.0
FORA_DA_LINHA_M = 40.0
MIN_PARA_VALER_S = 60.0       # previsão andada para o ritmo de hoje começar a contar
MIN_PARA_APRENDER_S = 120.0   # ... e para a viagem mudar o fator guardado


def _limitar(f):
    return max(FATOR_MIN, min(FATOR_MAX, f))


class Ritmo:
    def __init__(self, fator=1.0):
        try:
            self.aprendido = _limitar(float(fator))
        except (TypeError, ValueError):
            self.aprendido = 1.0
        self.comecar()

    def comecar(self):
        """Zera a medição da viagem (o fator aprendido fica)."""
        self._real_s = self._previsto_s = 0.0
        self._nav = self._rota = self._t = None
        self._dist = self._parado_s = 0.0
        rotas.fator_ritmo = self.aprendido

    def leitura(self, nav, vel_kmh, agora):
        """A cada posição do GPS durante a navegação (depois de nav.atualizar)."""
        rota = nav.rota
        if nav is not self._nav or rota is not self._rota:
            # começou, recalculou ou trocou de rota: a distância recomeça
            self._nav, self._rota, self._dist, self._t = nav, rota, nav.dist_feita, agora
            return
        dt, avanco = agora - self._t, nav.dist_feita - self._dist
        self._t, self._dist = agora, nav.dist_feita
        if not 0 < dt < 5 or nav.dist_da_linha > FORA_DA_LINHA_M or rota.total_m <= 0:
            return
        if vel_kmh < 2.0:
            self._parado_s += dt
            if self._parado_s > PARADA_CONTA_S:
                return
        else:
            self._parado_s = 0.0
        self._real_s += dt
        self._previsto_s += rota.tempo_base_s * avanco / rota.total_m
        rotas.fator_ritmo = self.fator_agora()

    def _de_hoje(self):
        return _limitar(self._real_s / self._previsto_s)

    def fator_agora(self):
        if self._previsto_s < MIN_PARA_VALER_S:
            return self.aprendido
        peso = min(0.6, self._previsto_s / 600.0)
        return _limitar(self.aprendido * (1 - peso) + self._de_hoje() * peso)

    def terminar(self):
        """Fim da navegação: devolve o fator aprendido (para guardar)."""
        if self._previsto_s >= MIN_PARA_APRENDER_S:
            peso = min(0.5, self._previsto_s / 1200.0)
            self.aprendido = _limitar(self.aprendido * (1 - peso) + self._de_hoje() * peso)
        self.comecar()
        return self.aprendido
