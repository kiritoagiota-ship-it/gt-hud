"""Semáforos, lombadas e radares de Goiânia (dados/goiania_sinais.json, do
OpenStreetMap, gerado por ferramentas/gerar_goiania.py).

Os tipos: "semaforo", "lombada" e "radarNN" (NN = limite em km/h; "radar0"
quando o mapa não informa o limite). Use e_radar() e limite_do_radar().

- ao_longo(rota): os que ficam EM CIMA da rota, com a distância desde o
  começo (a navegação avisa "Semáforo à frente" / "Lombada à frente").
- na_caixa(...): os que estão na área vista (o mapa desenha os ícones).
Os pontos ficam numa grade (~110 m) para não comparar cada trecho da rota
com os ~1700 pontos da cidade.
"""
import json
import math
import os

ARQUIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados", "goiania_sinais.json")
CELULA = 0.001        # graus (~110 m)
NA_ROTA_M = 14        # até isso da linha da rota: está no caminho
JUNTAR_M = 80         # cruzamento com vários semáforos (ou dois colados): um aviso só
_M_GRAU = 111320.0

_grade = None


def _carregar():
    global _grade
    if _grade is not None:
        return _grade
    _grade = {}
    try:
        with open(ARQUIVO, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return _grade
    for tipo, chave in (("semaforo", "semaforos"), ("lombada", "lombadas")):
        for lat, lon in dados.get(chave, []):
            _grade.setdefault((int(lat // CELULA), int(lon // CELULA)), []).append((lat, lon, tipo))
    for lat, lon, limite in dados.get("radares", []):
        _grade.setdefault((int(lat // CELULA), int(lon // CELULA)), []).append(
            (lat, lon, "radar%d" % limite))
    return _grade


def e_radar(tipo):
    return tipo.startswith("radar")


def limite_do_radar(tipo):
    """km/h do radar, ou 0 se o mapa não informa."""
    try:
        return int(tipo[5:])
    except ValueError:
        return 0


def na_caixa(lat0, lon0, lat1, lon1, limite=80, so_radares=False):
    """[(lat, lon, tipo)] dentro do retângulo (no máximo `limite`)."""
    grade = _carregar()
    achados = []
    if (lat1 - lat0) / CELULA * ((lon1 - lon0) / CELULA) > 40000:
        return achados   # área grande demais (mapa muito de longe)
    for i in range(int(lat0 // CELULA), int(lat1 // CELULA) + 1):
        for j in range(int(lon0 // CELULA), int(lon1 // CELULA) + 1):
            for p in grade.get((i, j), ()):
                if so_radares and not e_radar(p[2]):
                    continue
                if lat0 <= p[0] <= lat1 and lon0 <= p[1] <= lon1:
                    achados.append(p)
                    if len(achados) >= limite:
                        return achados
    return achados


def ao_longo(rota):
    """[(dist_m desde o começo, tipo)] dos semáforos/lombadas no caminho."""
    grade = _carregar()
    if not grade or len(rota.pontos) < 2:
        return []
    achados = {}
    for i, (a, b) in enumerate(zip(rota.pontos, rota.pontos[1:])):
        k = math.cos(math.radians(a[0])) * _M_GRAU
        bx, by = (b[1] - a[1]) * k, (b[0] - a[0]) * _M_GRAU
        c2 = bx * bx + by * by
        celulas = {(int(p[0] // CELULA) + di, int(p[1] // CELULA) + dj)
                   for p in (a, b) for di in (-1, 0, 1) for dj in (-1, 0, 1)}
        for cel in celulas:
            for lat, lon, tipo in grade.get(cel, ()):
                px, py = (lon - a[1]) * k, (lat - a[0]) * _M_GRAU
                t = 0.0 if c2 == 0 else max(0.0, min(1.0, (px * bx + py * by) / c2))
                d = math.hypot(px - t * bx, py - t * by)
                if d <= NA_ROTA_M:
                    dist = rota.acumulado[i] + t * (rota.acumulado[i + 1] - rota.acumulado[i])
                    chave = (lat, lon)
                    if chave not in achados or dist < achados[chave][0]:
                        achados[chave] = (dist, tipo)
    lista = sorted(achados.values())
    juntos = []
    for dist, tipo in lista:
        if juntos and juntos[-1][1] == tipo and dist - juntos[-1][0] < JUNTAR_M:
            continue
        juntos.append((dist, tipo))
    return juntos
