"""Rota de bike: pede ao Valhalla do OpenStreetMap (grátis, sem conta), lê
as manobras e acha as subidas pela altimetria da rota.

Perfil escolhido pelo dono: caminho mais rápido (sem evitar subida nem
avenida). O Valhalla devolve também a elevação a cada ELEVACAO_PASSO_M ao
longo da rota; é dela que saem as subidas.
"""
import json
import math
import urllib.error
import urllib.parse

import rede


class SemRota(Exception):
    """O servidor respondeu, mas não há caminho de bike até lá (não é falta
    de internet)."""

VALHALLA = "https://valhalla1.openstreetmap.de/route"
ELEVACAO_PASSO_M = 30
# subida que merece aviso: inclinação média >= SUBIDA_GRAU_MIN em pelo menos
# SUBIDA_COMPR_MIN_M, ganhando SUBIDA_GANHO_MIN_M ou mais de altura
SUBIDA_GRAU_MIN = 3.0
SUBIDA_COMPR_MIN_M = 60
SUBIDA_GANHO_MIN_M = 4.0
SUBIDA_EMENDA_M = 45   # subidas separadas por menos que isso viram uma só

# tipos de manobra do Valhalla -> ação usada no painel e na voz
_ACOES = {
    1: "em_frente", 2: "direita", 3: "esquerda",
    4: "chegada", 5: "chegada_direita", 6: "chegada_esquerda",
    7: "em_frente", 8: "em_frente",
    9: "levemente_direita", 10: "direita", 11: "acentuada_direita",
    12: "retorno", 13: "retorno", 14: "acentuada_esquerda", 15: "esquerda",
    16: "levemente_esquerda", 17: "em_frente", 18: "saida_direita", 19: "saida_esquerda",
    20: "saida_direita", 21: "saida_esquerda", 22: "em_frente",
    23: "mantenha_direita", 24: "mantenha_esquerda", 25: "em_frente",
    26: "rotatoria", 27: "sair_rotatoria", 37: "mantenha_direita", 38: "mantenha_esquerda",
}


def distancia_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371000.0 * math.asin(math.sqrt(h))


def decodificar_polyline(texto, precisao=1e6):
    """Formato "polyline6" do Valhalla -> [(lat, lon), ...]."""
    pontos, i, lat, lon = [], 0, 0, 0
    while i < len(texto):
        valores = []
        for _ in range(2):
            resultado = deslocamento = 0
            while True:
                b = ord(texto[i]) - 63
                i += 1
                resultado |= (b & 0x1F) << deslocamento
                deslocamento += 5
                if b < 0x20:
                    break
            valores.append(~(resultado >> 1) if resultado & 1 else resultado >> 1)
        lat += valores[0]
        lon += valores[1]
        pontos.append((lat / precisao, lon / precisao))
    return pontos


def achar_subidas(elevacao, passo=ELEVACAO_PASSO_M):
    """[{inicio_m, fim_m, ganho_m, grau}] a partir da elevação a cada `passo` m."""
    if len(elevacao) < 3:
        return []
    # média de 3 amostras: o modelo de relevo tem degraus de ~1 m
    e = ([elevacao[0]]
         + [(elevacao[i - 1] + elevacao[i] + elevacao[i + 1]) / 3.0
            for i in range(1, len(elevacao) - 1)]
         + [elevacao[-1]])
    trechos, inicio = [], None
    for i in range(1, len(e)):
        subindo = (e[i] - e[i - 1]) / passo * 100.0 >= SUBIDA_GRAU_MIN
        if subindo and inicio is None:
            inicio = i - 1
        elif not subindo and inicio is not None:
            trechos.append([inicio, i - 1])
            inicio = None
    if inicio is not None:
        trechos.append([inicio, len(e) - 1])
    emendados = []
    for t in trechos:
        if emendados and (t[0] - emendados[-1][1]) * passo < SUBIDA_EMENDA_M:
            emendados[-1][1] = t[1]
        else:
            emendados.append(t)
    subidas = []
    for a, b in emendados:
        compr = (b - a) * passo
        ganho = e[b] - e[a]
        if compr >= SUBIDA_COMPR_MIN_M and ganho >= SUBIDA_GANHO_MIN_M:
            subidas.append({"inicio_m": a * passo, "fim_m": b * passo,
                            "ganho_m": ganho, "grau": ganho / compr * 100.0})
    return subidas


class Rota:
    def __init__(self, pontos, manobras, elevacao, tempo_s, destino_nome=""):
        self.pontos = pontos
        self.acumulado = [0.0]
        for a, b in zip(pontos, pontos[1:]):
            self.acumulado.append(self.acumulado[-1] + distancia_m(a, b))
        self.total_m = self.acumulado[-1]
        self.tempo_s = tempo_s
        self.destino_nome = destino_nome
        self.elevacao = elevacao
        self.subidas = achar_subidas(elevacao)
        self.subida_total_m = sum(max(0.0, b - a) for a, b in zip(elevacao, elevacao[1:]))
        for m in manobras:
            m["dist_m"] = self.acumulado[min(m["indice"], len(self.acumulado) - 1)]
        self.manobras = manobras

    @classmethod
    def do_valhalla(cls, dados, destino_nome=""):
        trecho = dados["trip"]["legs"][0]
        pontos = decodificar_polyline(trecho["shape"])
        manobras = []
        for m in trecho["maneuvers"]:
            manobras.append({
                "acao": _ACOES.get(m.get("type"), "em_frente"),
                "indice": m.get("begin_shape_index", 0),
                "texto": m.get("instruction", ""),
                "ruas": ", ".join(m.get("street_names") or []),
                "saida": m.get("roundabout_exit_count"),
            })
        return cls(pontos, manobras, trecho.get("elevation") or [],
                   dados["trip"]["summary"].get("time", 0), destino_nome)

    def subida_restante_m(self, dist_feita):
        """Quanto ainda falta subir a partir de dist_feita (soma das subidas)."""
        i0 = int(dist_feita // ELEVACAO_PASSO_M)
        e = self.elevacao
        return sum(max(0.0, e[i + 1] - e[i]) for i in range(max(0, i0), len(e) - 1))


def pedir_rota(origem, destino, rumo=None, destino_nome=""):
    """Chamada que espera a resposta (use rede.em_segundo_plano)."""
    partida = {"lat": origem[0], "lon": origem[1]}
    if rumo is not None:
        # já pedalando: evita uma rota que comece com meia-volta
        partida.update(heading=int(rumo) % 360, heading_tolerance=60)
    pedido = {
        "locations": [partida, {"lat": destino[0], "lon": destino[1]}],
        "costing": "bicycle",
        "costing_options": {"bicycle": {
            "bicycle_type": "Hybrid", "cycling_speed": 22,   # bike elétrica na cidade
            "use_roads": 0.75, "use_hills": 0.5, "avoid_bad_surfaces": 0.25}},
        "language": "pt-BR",
        "directions_options": {"language": "pt-BR", "units": "kilometers"},
        "elevation_interval": ELEVACAO_PASSO_M,
    }
    url = VALHALLA + "?json=" + urllib.parse.quote(json.dumps(pedido))
    try:
        dados = rede.baixar_json(url, timeout=25)
    except urllib.error.HTTPError as e:
        if e.code == 400:  # ex.: "No path could be found for input" (erro 442)
            try:
                codigo = json.loads(e.read().decode("utf-8")).get("error_code")
            except ValueError:
                codigo = None
            if codigo == 154:
                raise SemRota("Longe demais: rota de bike vai ate 150 km.")
            raise SemRota("Nao achei um caminho de bike ate esse lugar.")
        raise
    return Rota.do_valhalla(dados, destino_nome)
