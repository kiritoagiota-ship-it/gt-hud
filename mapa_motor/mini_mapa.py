"""Ruas em volta da pessoa, para o mini mapa do painel flutuante.

O painel (java/.../PainelFlutuante.java) fica por cima dos outros apps e não
tem como usar o mapa do app. Para ele não mostrar só o traçado da rota num
fundo vazio, daqui saem as RUAS de perto, tiradas dos mesmos arquivos de
mapa que o app já baixou (tiles vetoriais, zoom 14): linhas em metros a
partir de uma âncora, a mesma usada para o traçado da rota.

Só Python puro (sem tela): roda numa thread à parte e pode ser testado.
"""
import collections
import math

import mvt

Z = 14
RAIO_M = 430            # ruas até essa distância entram
JUNTAR_M = 7.0          # pontos mais juntos que isso viram um só (menos dados para o painel)
MAX_TILES_GUARDADOS = 6
GRAU_M = 111195.0       # metros por grau (a mesma esfera das distâncias da rota)
# classe da via no mapa -> grossura no painel (0 = não desenha)
GROSSURA = {"motorway": 3, "trunk": 3, "primary": 3, "secondary": 2, "tertiary": 2,
            "minor": 1, "service": 1, "busway": 1}

_tiles = collections.OrderedDict()   # (x, y) -> [(grossura, [(lat, lon), ...]), ...]


def tile_de(lat, lon):
    n = 2 ** Z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def _geo(tx, ty, px, py, extent):
    n = 2 ** Z
    mx, my = (tx + px / extent) / n, (ty + py / extent) / n
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * my)))), mx * 360.0 - 180.0


def linhas_do_tile(dados, tx, ty):
    """Arquivo do tile -> [(grossura, [(lat, lon), ...])] das ruas."""
    camadas = mvt.ler(dados, ("transportation",))
    if "transportation" not in camadas:
        return []
    extent, feicoes = camadas["transportation"]
    linhas = []
    for tipo, props, partes in feicoes:
        grossura = GROSSURA.get(props.get("class"), 0)
        if tipo != 2 or not grossura:
            continue
        for parte in partes:
            pontos = [_geo(tx, ty, parte[i], parte[i + 1], extent) for i in range(0, len(parte) - 1, 2)]
            if len(pontos) >= 2:
                linhas.append((grossura, pontos))
    return linhas


def _do_tile(ler, tx, ty):
    chave = (tx, ty)
    if chave in _tiles:
        _tiles.move_to_end(chave)
        return _tiles[chave]
    dados = ler(Z, tx, ty)
    if dados is None:
        return []           # sem o arquivo (e sem internet): tenta de novo na próxima
    linhas = linhas_do_tile(dados, tx, ty)
    _tiles[chave] = linhas
    while len(_tiles) > MAX_TILES_GUARDADOS:
        _tiles.popitem(last=False)
    return linhas


def ruas_perto(ler, lat, lon, ancora, raio_m=RAIO_M):
    """Ruas até raio_m de (lat, lon): [(grossura, [(x, y), ...])] em metros
    (leste, norte) a partir da âncora (lat, lon). `ler(z, x, y)` devolve o
    arquivo do tile (ou None)."""
    lat_a, lon_a = ancora
    k = math.cos(math.radians(lat_a)) * GRAU_M
    cx, cy = (lon - lon_a) * k, (lat - lat_a) * GRAU_M
    dlat, dlon = raio_m / GRAU_M, raio_m / k
    cantos = {tile_de(lat + a, lon + b) for a in (-dlat, dlat) for b in (-dlon, dlon)}
    ruas = []
    for tx, ty in sorted(cantos):
        for grossura, pontos in _do_tile(ler, tx, ty):
            trecho, ultimo = [], None
            for plat, plon in pontos:
                x, y = (plon - lon_a) * k, (plat - lat_a) * GRAU_M
                dentro = abs(x - cx) <= raio_m and abs(y - cy) <= raio_m
                if not dentro:
                    if len(trecho) >= 2:
                        ruas.append((grossura, trecho))
                    trecho, ultimo = [], None
                    continue
                if ultimo is None or abs(x - ultimo[0]) + abs(y - ultimo[1]) >= JUNTAR_M:
                    trecho.append((x, y))
                    ultimo = (x, y)
            if len(trecho) >= 2:
                ruas.append((grossura, trecho))
    return ruas


def em_texto(ruas):
    """Para mandar ao painel: "g:x,y x,y x,y;g:x,y x,y..." (metros inteiros)."""
    return ";".join("%d:%s" % (g, " ".join("%d,%d" % (round(x), round(y)) for x, y in pts))
                    for g, pts in ruas)
