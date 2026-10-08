"""O app aprende com as viagens do dono (escolhido por ele em 08/10/2026).

De cada viagem gravada (posição e hora, 1 por segundo) sai, para cada
quadradinho de ~110 m por onde ele passou, quantos metros andou e quanto
tempo levou, separado por faixa de horário (pico da manhã, tarde, noite,
fim de semana...). Com isso:
- o TEMPO de uma rota nova usa a velocidade que ELE costuma fazer em cada
  trecho que já conhece (semáforo demorado e ladeira entram na conta);
- dá para dizer "este trecho costuma estar lento neste horário".

Fica tudo no celular (o mesmo banco das viagens). Só vale a partir da 2a
passagem por um lugar, e só entra no tempo da rota quando ele já conhece
pelo menos COBERTURA_MIN dela.
"""
import contextlib
import math
import sqlite3
import threading
import time

from rota import distancia_m

CELULA = 0.001             # graus (~110 m)
PASSO_M = 40.0             # a rota é conferida a cada isso
VIAGENS_MIN = 2            # menos passagens que isso num lugar: ainda não confia
COBERTURA_MIN = 0.30       # conhece menos que isso da rota: fica o tempo do servidor
PARADA_LONGA_S = 90.0      # parado mais que isso não é trânsito (estacionou, conversou)
LENTO = 0.5                # trecho "lento": abaixo dessa fração do ritmo normal dele
LENTO_MIN_M = 120.0
RITMO_PADRAO_MS = 5.5      # até ele ter histórico (~20 km/h com as paradas)

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS trechos (
    cla INTEGER, clo INTEGER, faixa INTEGER,
    metros REAL, segundos REAL, viagens INTEGER,
    PRIMARY KEY (cla, clo, faixa)
);
"""


def faixa_de(t):
    """Faixa de horário (0 a 9) da hora `t` (segundos, relógio do celular):
    madrugada, pico da manhã, dia, pico da tarde, noite; +5 no fim de semana."""
    h = time.localtime(t)
    hora = h.tm_hour
    parte = 0 if hora < 6 else 1 if hora < 9 else 2 if hora < 16 else 3 if hora < 20 else 4
    return parte + (5 if h.tm_wday >= 5 else 0)


def _celula(lat, lon):
    return int(math.floor(lat / CELULA)), int(math.floor(lon / CELULA))


class Aprendizado:
    def __init__(self, caminho_banco):
        self.caminho = caminho_banco
        self._trava = threading.Lock()
        self._ritmo = None
        with self._conectar() as c:
            c.executescript(_ESQUEMA)

    @contextlib.contextmanager
    def _conectar(self):
        """Abre, grava e FECHA (o `with` do sqlite3 sozinho não fecha a conexão)."""
        con = sqlite3.connect(self.caminho)
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # --- aprender ------------------------------------------------------------------
    def aprender(self, pontos):
        """pontos: [(lat, lon, km/h, hora)] de UMA viagem, em ordem."""
        soma = {}
        parado_s = 0.0
        for a, b in zip(pontos, pontos[1:]):
            dt = b[3] - a[3]
            if not 0 < dt < 10:
                continue
            d = distancia_m((a[0], a[1]), (b[0], b[1]))
            vel_ms = max(0.0, (b[2] or 0.0)) / 3.6
            d = min(d, vel_ms * dt * 1.5 + 2.0)      # salto do GPS não vira distância
            if vel_ms < 0.6:
                parado_s += dt
                if parado_s > PARADA_LONGA_S:
                    continue                          # o que passar disso não é do trânsito
                d = 0.0
            else:
                parado_s = 0.0
            chave = _celula((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0) + (faixa_de(b[3]),)
            m, s = soma.get(chave, (0.0, 0.0))
            soma[chave] = (m + d, s + dt)
        if not soma:
            return 0
        with self._trava, self._conectar() as c:
            for (cla, clo, faixa), (m, s) in soma.items():
                c.execute("INSERT INTO trechos (cla, clo, faixa, metros, segundos, viagens) VALUES (?,?,?,?,?,1) "
                          "ON CONFLICT(cla, clo, faixa) DO UPDATE SET metros = metros + excluded.metros, "
                          "segundos = segundos + excluded.segundos, viagens = viagens + 1",
                          (cla, clo, faixa, m, s))
        self._ritmo = None
        return len(soma)

    # --- consultar -----------------------------------------------------------------
    def ritmo_normal_ms(self):
        """A velocidade típica dele (m/s, com as paradas), de tudo que já andou."""
        if self._ritmo is None:
            with self._conectar() as c:
                m, s = c.execute("SELECT SUM(metros), SUM(segundos) FROM trechos").fetchone()
            self._ritmo = (m / s) if (m and s and m > 3000) else RITMO_PADRAO_MS
        return self._ritmo

    def _velocidades(self, celulas, faixa):
        """{célula: m/s} das células conhecidas: da faixa de horário pedida se
        já houver passagens bastantes nela; senão, de todos os horários."""
        if not celulas:
            return {}
        clas = [c[0] for c in celulas]
        clos = [c[1] for c in celulas]
        with self._conectar() as c:
            linhas = c.execute(
                "SELECT cla, clo, faixa, metros, segundos, viagens FROM trechos "
                "WHERE cla BETWEEN ? AND ? AND clo BETWEEN ? AND ?",
                (min(clas), max(clas), min(clos), max(clos))).fetchall()
        da_faixa, de_todas = {}, {}
        for cla, clo, f, m, s, n in linhas:
            chave = (cla, clo)
            if chave not in celulas:
                continue
            a = de_todas.get(chave, (0.0, 0.0, 0))
            de_todas[chave] = (a[0] + m, a[1] + s, a[2] + n)
            if f == faixa:
                da_faixa[chave] = (m, s, n)
        vel = {}
        for chave, (m, s, n) in de_todas.items():
            if chave in da_faixa and da_faixa[chave][2] >= VIAGENS_MIN:
                m, s, n = da_faixa[chave]
            if n >= VIAGENS_MIN and s >= 4.0 and m >= 15.0:
                vel[chave] = max(0.8, m / s)
        return vel

    def avaliar(self, rota, quando=None):
        """Olha a rota com o histórico dele: {"cobertura" (0..1 da rota que ele
        já conhece), "tempo_s" (ou None), "lentos" [(início m, fim m)] e
        "extra_s" (quanto os trechos lentos somam além do ritmo normal)}."""
        if rota.total_m <= 0:
            return {"cobertura": 0.0, "tempo_s": None, "lentos": [], "extra_s": 0.0}
        faixa = faixa_de(time.time() if quando is None else quando)
        amostras = []
        d = PASSO_M / 2.0
        while d < rota.total_m:
            lat, lon, _ = rota.ponto_em(d)
            amostras.append((d, _celula(lat, lon)))
            d += PASSO_M
        vel = self._velocidades({c for _, c in amostras}, faixa)
        normal = self.ritmo_normal_ms()
        base = rota.total_m / rota.tempo_s if rota.tempo_s > 0 else normal   # trecho que ele não conhece
        tempo, conhecidos = 0.0, 0
        lentos, extra, corrente = [], 0.0, None
        for d, cel in amostras:
            v = vel.get(cel)
            if v is None:
                tempo += PASSO_M / base
                lento = False
            else:
                conhecidos += 1
                tempo += PASSO_M / v
                lento = v < normal * LENTO
                if lento:
                    extra += PASSO_M / v - PASSO_M / normal
            if lento:
                corrente = [corrente[0] if corrente else d - PASSO_M / 2.0, d + PASSO_M / 2.0]
            elif corrente is not None:
                if corrente[1] - corrente[0] >= LENTO_MIN_M:
                    lentos.append(tuple(corrente))
                corrente = None
        if corrente is not None and corrente[1] - corrente[0] >= LENTO_MIN_M:
            lentos.append(tuple(corrente))
        cobertura = conhecidos / float(len(amostras)) if amostras else 0.0
        return {"cobertura": cobertura, "tempo_s": tempo if cobertura >= COBERTURA_MIN else None,
                "lentos": lentos, "extra_s": extra if lentos else 0.0}
