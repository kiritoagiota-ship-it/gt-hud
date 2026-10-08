"""Ruas coloridas pela velocidade de AGORA (pedido do dono em 07/10/2026,
"como no Waze e no Google Maps"): TomTom Traffic Flow, em pedaços vetoriais
(Vector Flow Tiles v4, tipo "relative": a velocidade de agora dividida pela
velocidade com a via livre, de 0 a 1).

Só avenidas e vias de ligação (ROAD_TYPES): rua de bairro quase não tem
medição e encheria o mapa de risco. Cada pedaço (zoom Z) vale VALIDADE_S; o
plano gratuito da TomTom dá 50 mil pedaços por dia e o app usa poucas dezenas
por hora.

Feito pela documentação (docs.tomtom.com/traffic-api, "Vector Flow Tiles"):
a resposta de verdade só existe com a chave, no celular.
"""
import math
import threading
import time
import urllib.error

import goiania
import mvt
import rede

URL = "https://api.tomtom.com/traffic/map/4/tile/flow/relative/%d/%d/%d.pbf?key=%s&roadTypes=%s"
ROAD_TYPES = "%5B0,1,2,3,4%5D"   # [0,1,2,3,4]: de via expressa até via de ligação
CAMADA = "Traffic flow"
Z = 12                     # um pedaço cobre ~10 km: Goiânia inteira são 25
VALIDADE_S = 180.0
MAX_POR_VEZ = 4            # pedaços novos pedidos de cada vez
TRECHO_MIN_M = 25.0        # trecho medido mais curto que isso vira um "quadradinho" solto no mapa: fica de fora
PARADO, LENTO, MODERADO, LIVRE, FECHADA = 3, 2, 1, 0, 4


def nivel_de(fracao, fechada=False):
    """0 livre (verde), 1 moderado (amarelo), 2 lento (laranja), 3 parado
    (vermelho), 4 via fechada."""
    if fechada:
        return FECHADA
    if fracao < 0.35:
        return PARADO
    if fracao < 0.55:
        return LENTO
    return MODERADO if fracao < 0.75 else LIVRE


def tile_de(lat, lon, z=Z):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def tiles_da_caixa(lat0, lon0, lat1, lon1, z=Z):
    """Os pedaços (x, y) que cobrem a caixa, só dentro de Goiânia."""
    g0, h0, g1, h1 = goiania.LIMITES
    lat0, lon0, lat1, lon1 = max(lat0, g0), max(lon0, h0), min(lat1, g1), min(lon1, h1)
    if lat0 > lat1 or lon0 > lon1:
        return []
    xa, ya = tile_de(lat1, lon0, z)
    xb, yb = tile_de(lat0, lon1, z)
    return [(x, y) for x in range(xa, xb + 1) for y in range(ya, yb + 1)]


def _comprimento_m(pontos):
    total = 0.0
    for (la0, lo0), (la1, lo1) in zip(pontos, pontos[1:]):
        total += math.hypot((la1 - la0) * 111320.0, (lo1 - lo0) * 111320.0 * math.cos(math.radians(la0)))
    return total


def segmentos_da_camada(camada, x, y, z=Z):
    """A camada "Traffic flow" de um pedaço -> [(pontos [(lat, lon)], nível)]."""
    if not camada:
        return []
    extent, feicoes = camada
    n = 2.0 ** z
    saida = []
    for tipo, props, partes in feicoes:
        if tipo != 2:
            continue
        nivel = nivel_de(float(props.get("traffic_level", 1.0) or 0.0), bool(props.get("road_closure")))
        for parte in partes:
            pontos = []
            for i in range(0, len(parte) - 1, 2):
                mx = (x + parte[i] / float(extent)) / n
                my = (y + parte[i + 1] / float(extent)) / n
                pontos.append((math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * my)))), mx * 360.0 - 180.0))
            if len(pontos) >= 2 and _comprimento_m(pontos) >= TRECHO_MIN_M:
                saida.append((pontos, nivel))
    return saida


class SemChave(Exception):
    """A TomTom recusou a chave para o trânsito em cores."""


class Fluxo:
    """Guarda os pedaços já baixados e pede os que faltam para a vista."""

    def __init__(self, baixar=None):
        self._baixar = baixar or rede.baixar
        self._tiles = {}            # (x, y) -> (hora, [(pontos, nível)])
        self._pedindo = set()
        self._trava = threading.Lock()
        self.recusada = False       # a chave não vale para isto: para de pedir

    def buscar_tile(self, chave, x, y):
        """Chamada que espera a resposta (thread). Guarda e devolve os segmentos."""
        try:
            dados = self._baixar(URL % (Z, x, y, chave, ROAD_TYPES), 12)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                self.recusada = True
                raise SemChave("A TomTom recusou a chave.")
            raise
        segmentos = segmentos_da_camada(mvt.ler(dados, (CAMADA,)).get(CAMADA), x, y)
        with self._trava:
            self._tiles[(x, y)] = (time.monotonic(), segmentos)
        return segmentos

    def faltam(self, tiles, agora=None):
        """Dos pedaços da vista, os que não tem ou que já estão velhos."""
        agora = time.monotonic() if agora is None else agora
        with self._trava:
            return [t for t in tiles if t not in self._pedindo
                    and (t not in self._tiles or agora - self._tiles[t][0] >= VALIDADE_S)][:MAX_POR_VEZ]

    def atualizar(self, chave, tiles, ao_terminar):
        """Pede (em segundo plano) o que falta da lista; ao_terminar(mudou) é
        chamado pelo rede.em_segundo_plano quando acaba."""
        if self.recusada or not chave:
            return False
        pedir = self.faltam(tiles)
        if not pedir:
            return False
        with self._trava:
            self._pedindo.update(pedir)

        def trabalhar():
            mudou = False
            try:
                for x, y in pedir:
                    try:
                        self.buscar_tile(chave, x, y)
                        mudou = True
                    except SemChave:
                        break
                    except Exception as e:   # (sem o texto: o endereço leva a chave)
                        print("[fluxo] pedaço %d/%d:" % (x, y), type(e).__name__, getattr(e, "code", ""))
            finally:
                with self._trava:
                    self._pedindo.difference_update(pedir)
            return mudou
        rede.em_segundo_plano(trabalhar, ao_terminar, lambda e: None)
        return True

    def segmentos(self, tiles):
        """Tudo o que há guardado para esses pedaços: [(pontos, nível)]."""
        with self._trava:
            return [s for t in tiles for s in self._tiles.get(t, (0, []))[1]]

    def esquecer(self):
        with self._trava:
            self._tiles.clear()
        self.recusada = False
