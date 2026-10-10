"""Quantos km a moto rodou desde a última carga completa.

O app não conversa com a bateria da GT20: quem avisa é o dono. Ele toca em
"Carreguei 100%" ao tirar da tomada, e em "Caiu uma barrinha" cada vez que o
painel da moto perde uma das 5 barrinhas. O app conta os km (pelo GPS, com ou
sem rota) e guarda com quantos km cada barrinha caiu. Com isso, e com a sobra
informada na hora de recarregar, dá para estimar a autonomia REAL dele (a de
fábrica, 60 km, é medida devagar e no plano).

Só conta com o app recebendo o GPS: aberto, ou minimizado (com uma carga sendo
contada, segundo_plano.py mantém o GPS mesmo sem rota). Fechado, não conta.
"""
import time

from viagem import LIMIAR_MOVIMENTO_KMH, VELOCIDADE_IMPOSSIVEL_KMH, haversine_m

BARRAS = 5
GRAVAR_A_CADA_M = 150.0     # de quanto em quanto grava no arquivo (não a cada leitura do GPS)
CARGA_MINIMA_M = 300.0      # carga com menos que isso não entra no histórico (toque sem querer)
HISTORICO_MAX = 40
CARGAS_NA_MEDIA = 5         # a autonomia estimada usa as últimas cargas


def _km(metros):
    return ("%.1f km" % (metros / 1000.0)).replace(".", ",")


class Bateria:
    """O estado fica em ajustes["bateria"] (a carga de agora, None = nunca marcou)
    e ajustes["bateria_cargas"] (as cargas que já terminaram)."""

    def __init__(self, ajustes, relogio=time.time):
        self.ajustes = ajustes
        self._relogio = relogio
        self._ultimo = None       # (lat, lon, t) da leitura anterior
        self._gravado_m = 0.0
        carga = ajustes["bateria"]
        self.carga = dict(carga) if isinstance(carga, dict) else None
        if self.carga is not None:
            self.carga["quedas"] = list(self.carga.get("quedas") or [])
            self._gravado_m = self.carga.get("m", 0.0)

    # --- leitura --------------------------------------------------------
    @property
    def ativa(self):
        return self.carga is not None

    @property
    def metros(self):
        return self.carga["m"] if self.carga else 0.0

    @property
    def barras(self):
        """Quantas barrinhas o painel da moto deve estar mostrando."""
        return BARRAS - len(self.carga["quedas"]) if self.carga else BARRAS

    @property
    def vel_media_kmh(self):
        if not self.carga or self.carga.get("mov_s", 0) <= 0:
            return 0.0
        return self.carga["m"] / self.carga["mov_s"] * 3.6

    def km_por_barra(self):
        """Quantos metros cada barrinha que já caiu durou: [1ª, 2ª, ...]."""
        if not self.carga:
            return []
        antes, duracoes = 0.0, []
        for m in self.carga["quedas"]:
            duracoes.append(max(0.0, m - antes))
            antes = m
        return duracoes

    def autonomia_m(self):
        """Estimativa da carga inteira, em metros (None = ainda não dá para saber).
        Das cargas terminadas: km rodados / barrinhas gastas x 5. Sem nenhuma
        ainda, usa as barrinhas que já caíram na carga de agora."""
        estimativas = []
        for c in self.ajustes["bateria_cargas"][-CARGAS_NA_MEDIA:]:
            gastas = BARRAS - c.get("sobra", BARRAS)
            if gastas > 0 and c.get("m", 0) > 0:
                estimativas.append(c["m"] / gastas * BARRAS)
        if estimativas:
            return sum(estimativas) / len(estimativas)
        if self.carga and self.carga["quedas"]:
            return self.carga["quedas"][-1] / len(self.carga["quedas"]) * BARRAS
        return None

    def texto_curto(self):
        """O que vai no botão do mapa."""
        if not self.carga:
            return "Bateria"
        return "%d/%d  %s" % (self.barras, BARRAS, _km(self.carga["m"]))

    def texto(self):
        """O resumo da janela (até 4 linhas)."""
        if not self.carga:
            return ("Toque em \"Carreguei 100%\" quando tirar a moto da tomada com a carga cheia. "
                    "Daí em diante o app conta os km desta carga.")
        linhas = ["Nesta carga: %s" % _km(self.carga["m"])]
        if self.vel_media_kmh >= 1:
            linhas[0] += "  ·  média %d km/h" % round(self.vel_media_kmh)
        duracoes = self.km_por_barra()
        if duracoes:
            linhas.append("Barrinhas: %d de %d  ·  cada uma durou %s" % (
                self.barras, BARRAS, ", ".join(_km(d).replace(" km", "") for d in duracoes) + " km"))
        else:
            linhas.append("Barrinhas: %d de %d (avise quando cair uma)" % (self.barras, BARRAS))
        total = self.autonomia_m()
        if total:
            linhas.append("Carga inteira, pelo seu uso: uns %d km" % round(total / 1000.0))
        else:
            linhas.append("Carga inteira: ainda aprendendo com o seu uso")
        return "\n".join(linhas)

    def texto_historico(self, quantas=6):
        cargas = self.ajustes["bateria_cargas"][-quantas:]
        if not cargas:
            return "Nenhuma carga terminada ainda."
        linhas = []
        for c in reversed(cargas):
            dia = time.strftime("%d/%m", time.localtime(c.get("fim", 0)))
            linha = "%s: %s, sobraram %d de %d" % (dia, _km(c.get("m", 0)), c.get("sobra", 0), BARRAS)
            if c.get("media"):
                linha += ", média %d km/h" % round(c["media"])
            linhas.append(linha)
        return "\n".join(linhas)

    # --- o que o dono marca ----------------------------------------------
    def carregou(self, sobra=None):
        """Carga cheia agora. `sobra`: barrinhas que ainda tinha antes de carregar
        (a carga que termina vai para o histórico com esse número)."""
        if self.carga and self.carga["m"] >= CARGA_MINIMA_M:
            sobra = self.barras if sobra is None else max(0, min(BARRAS, int(sobra)))
            cargas = list(self.ajustes["bateria_cargas"])
            cargas.append({"inicio": self.carga.get("desde"), "fim": self._relogio(),
                           "m": round(self.carga["m"], 1), "sobra": sobra,
                           "quedas": [round(q, 1) for q in self.carga["quedas"]],
                           "media": round(self.vel_media_kmh, 1)})
            self.ajustes["bateria_cargas"] = cargas[-HISTORICO_MAX:]
        self.carga = {"desde": self._relogio(), "m": 0.0, "mov_s": 0.0, "quedas": []}
        self._ultimo = None
        self._gravar()

    def caiu_barra(self):
        """O painel da moto perdeu uma barrinha agora. False se não havia o que marcar."""
        if not self.carga or self.barras <= 0:
            return False
        self.carga["quedas"].append(self.carga["m"])
        self._gravar()
        return True

    def barra_esquecida(self, durou_m):
        """Uma barrinha caiu e o dono esqueceu de marcar na hora: ele informa quantos
        metros ela DUROU (pedido dele, 09/10/2026: "mais um pico deu 11 km"). Conta a
        partir da barrinha anterior. Se passar do que o app contou (ele andou com o app
        fechado), vale o número dele: a contagem da carga sobe até lá."""
        if not self.carga or self.barras <= 0 or not 0 < durou_m < 200000:
            return False
        caiu_em = (self.carga["quedas"][-1] if self.carga["quedas"] else 0.0) + durou_m
        self.carga["quedas"].append(caiu_em)
        self.carga["m"] = max(self.carga["m"], caiu_em)
        self._gravar()
        return True

    def desfazer_barra(self):
        if not self.carga or not self.carga["quedas"]:
            return False
        self.carga["quedas"].pop()
        self._gravar()
        return True

    # --- GPS ------------------------------------------------------------
    def registrar(self, lat, lon, vel_kmh, t=None):
        """Soma o trecho desde a leitura anterior (mesmas travas da gravação de
        viagem contra os saltos do GPS)."""
        if not self.carga:
            return
        t = time.monotonic() if t is None else t
        anterior, self._ultimo = self._ultimo, (lat, lon, t)
        if anterior is None:
            return
        dt = t - anterior[2]
        if not 0 < dt < 10 or vel_kmh < LIMIAR_MOVIMENTO_KMH:
            return
        d = haversine_m(anterior[0], anterior[1], lat, lon)
        if d / dt * 3.6 >= VELOCIDADE_IMPOSSIVEL_KMH:
            return
        self.carga["m"] += min(d, vel_kmh / 3.6 * dt * 1.5 + 2.0)
        self.carga["mov_s"] = self.carga.get("mov_s", 0.0) + dt
        if self.carga["m"] - self._gravado_m >= GRAVAR_A_CADA_M:
            self._gravar()

    def guardar(self):
        """Grava o que falta (ao minimizar ou fechar o app)."""
        if self.carga and self.carga["m"] != self._gravado_m:
            self._gravar()

    def _gravar(self):
        self._gravado_m = self.carga["m"]
        self.ajustes["bateria"] = dict(self.carga, quedas=list(self.carga["quedas"]))
