"""Goiânia: a área do app (pedido do dono: mapa, busca e rotas só em
Goiânia; fica mais leve e tudo pode vir junto no APK).

LIMITES = retângulo (lat_min, lon_min, lat_max, lon_max) com a cidade e uma
folga (pega as bordas de Aparecida, Trindade e Senador Canedo).
"""
LIMITES = (-16.86, -49.45, -16.48, -49.07)
CENTRO = (-16.6799, -49.2550)  # Praça Cívica


def dentro(lat, lon, folga=0.0):
    lat0, lon0, lat1, lon1 = LIMITES
    return lat0 - folga <= lat <= lat1 + folga and lon0 - folga <= lon <= lon1 + folga


def prender(lat, lon):
    """O ponto mais perto de (lat, lon) dentro de Goiânia."""
    lat0, lon0, lat1, lon1 = LIMITES
    return min(max(lat, lat0), lat1), min(max(lon, lon0), lon1)
