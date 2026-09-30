"""Gravação de uma viagem: distância, tempos, máxima e média."""
import math
import time

LIMIAR_MOVIMENTO_KMH = 2.0
VELOCIDADE_IMPOSSIVEL_KMH = 120.0  # salto de GPS acima disso é ignorado
# pausa automática: parada por PAUSA_AUTO_APOS_S pausa sozinha e volta a
# gravar quando passa de RETOMA_AUTO_KMH (um pouco acima do limiar, para
# não ficar pausando/retomando com o ruído do GPS parado)
PAUSA_AUTO_APOS_S = 5.0
RETOMA_AUTO_KMH = 3.0


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp_ = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp_ / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Viagem:
    PARADA = "parada"
    GRAVANDO = "gravando"
    PAUSADA = "pausada"

    def __init__(self, relogio=time.time):
        self._relogio = relogio
        self.estado = self.PARADA
        self._zerar()

    def _zerar(self):
        self.inicio = None
        self.distancia_m = 0.0
        self.vel_max_kmh = 0.0
        self.tempo_mov_s = 0.0
        self.pontos = []
        self._ultimo = None
        self._ultimo_t = None
        self._acumulado_s = 0.0
        self._retomada = None
        self.pausa_auto = False  # True = foi a pausa automática que pausou
        self._parado_desde = None

    # --- controle -------------------------------------------------------
    def iniciar(self):
        self._zerar()
        agora = self._relogio()
        self.inicio = agora
        self._retomada = agora
        self.estado = self.GRAVANDO

    def pausar(self, auto=False):
        if self.estado != self.GRAVANDO:
            return
        fim = self._relogio()
        if auto and self._parado_desde is not None:
            # os segundos esperando parado antes de pausar também não contam
            fim = max(self._retomada, self._parado_desde)
        self._acumulado_s += fim - self._retomada
        self._retomada = None
        self._ultimo = None  # não soma distância do trecho pausado
        self._parado_desde = None
        self.pausa_auto = auto
        self.estado = self.PAUSADA

    def retomar(self):
        if self.estado != self.PAUSADA:
            return
        self._retomada = self._relogio()
        self._parado_desde = None
        self.pausa_auto = False
        self.estado = self.GRAVANDO

    def checar_pausa_auto(self, vel_kmh, ligada=True):
        """Pausa sozinha depois de PAUSA_AUTO_APOS_S parada e retoma quando
        volta a andar (só se foi ela que pausou; a pausa do botão continua
        esperando o Retomar). Devolve True se o estado mudou."""
        if not ligada:
            self._parado_desde = None
            return False
        if self.estado == self.GRAVANDO:
            if vel_kmh >= LIMIAR_MOVIMENTO_KMH:
                self._parado_desde = None
                return False
            agora = self._relogio()
            if self._parado_desde is None:
                self._parado_desde = agora
            elif agora - self._parado_desde >= PAUSA_AUTO_APOS_S:
                self.pausar(auto=True)
                return True
        elif self.estado == self.PAUSADA and self.pausa_auto and vel_kmh >= RETOMA_AUTO_KMH:
            self.retomar()
            return True
        return False

    def finalizar(self):
        """Encerra e devolve (resumo, pontos) ou None se não havia viagem."""
        if self.estado == self.PARADA:
            return None
        if self.estado == self.GRAVANDO:
            self.pausar()
        resumo = {
            "inicio": self.inicio,
            "fim": self._relogio(),
            "distancia_m": self.distancia_m,
            "duracao_s": self._acumulado_s,
            "tempo_mov_s": self.tempo_mov_s,
            "vel_max_kmh": self.vel_max_kmh,
            "vel_media_kmh": self.vel_media_kmh,
        }
        pontos = list(self.pontos)
        self.estado = self.PARADA
        return resumo, pontos

    # --- dados ----------------------------------------------------------
    def registrar(self, lat, lon, vel_kmh, t=None):
        if self.estado != self.GRAVANDO:
            return
        t = self._relogio() if t is None else t
        if self._ultimo is not None:
            d = haversine_m(self._ultimo[0], self._ultimo[1], lat, lon)
            dt = t - self._ultimo_t
            if 0 < dt < 10:
                implicita = d / dt * 3.6
                if vel_kmh >= LIMIAR_MOVIMENTO_KMH and implicita < VELOCIDADE_IMPOSSIVEL_KMH:
                    self.distancia_m += d
                    self.tempo_mov_s += dt
        self.vel_max_kmh = max(self.vel_max_kmh, vel_kmh)
        self.pontos.append((lat, lon, vel_kmh, t))
        self._ultimo = (lat, lon)
        self._ultimo_t = t

    @property
    def tempo_total_s(self):
        extra = 0.0
        if self.estado == self.GRAVANDO and self._retomada is not None:
            extra = self._relogio() - self._retomada
        return self._acumulado_s + extra

    @property
    def vel_media_kmh(self):
        if self.tempo_mov_s <= 0:
            return 0.0
        return self.distancia_m / self.tempo_mov_s * 3.6
