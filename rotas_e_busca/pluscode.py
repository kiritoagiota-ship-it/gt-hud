"""Plus Code (Open Location Code), o código que o Google Maps mostra em todo
lugar (ex.: "9MJH+9W St. Morada do Sol, Goiânia"): marca o ponto com ~14 m
de precisão e se decodifica sem internet nem conta.

Algoritmo aberto (github.com/google/open-location-code). Aqui só o que o
app precisa: código completo ("58MG8PCW+22") e código curto ("9MJH+9W"),
que é completado com a cidade de referência (Goiânia).
"""
import re

ALFABETO = "23456789CFGHJMPQRVWX"
_RES = [20.0, 1.0, 0.05, 0.0025, 0.000125]   # graus de cada par de dígitos
PADRAO = re.compile(r"(?<![0-9A-Za-z])([23456789CFGHJMPQRVWXcfghjmpqrvwx]{4,8}\+"
                    r"[23456789CFGHJMPQRVWXcfghjmpqrvwx]{2,3})(?![0-9A-Za-z])")


def codificar(lat, lon):
    """(lat, lon) -> código completo de 10 dígitos ("58MG8PCW+22")."""
    lat = min(max(lat, -90.0), 89.9999999) + 90.0
    lon = (lon + 180.0) % 360.0
    codigo = ""
    for r in _RES:
        a, b = int(lat // r), int(lon // r)
        lat -= a * r
        lon -= b * r
        codigo += ALFABETO[a] + ALFABETO[b]
    return codigo[:8] + "+" + codigo[8:]


def decodificar(codigo):
    """Código completo -> (lat, lon) do centro do quadradinho."""
    d = codigo.replace("+", "").upper()
    lat, lon = -90.0, -180.0
    pares = min(len(d), 10) // 2
    for i in range(pares):
        lat += ALFABETO.index(d[2 * i]) * _RES[i]
        lon += ALFABETO.index(d[2 * i + 1]) * _RES[i]
    r = _RES[pares - 1]
    return lat + r / 2, lon + r / 2


def recuperar(codigo, ref_lat, ref_lon):
    """Código curto ou completo -> (lat, lon); o curto é completado com o
    ponto de referência (o lugar mais perto dele com esse código)."""
    codigo = codigo.upper()
    if codigo.index("+") == 8:
        return decodificar(codigo)
    falta = 8 - codigo.index("+")
    res = 20.0 ** (2 - falta / 2)
    lat, lon = decodificar(codificar(ref_lat, ref_lon)[:falta] + codigo)
    if ref_lat + res / 2 < lat:
        lat -= res
    elif ref_lat - res / 2 > lat:
        lat += res
    if ref_lon + res / 2 < lon:
        lon -= res
    elif ref_lon - res / 2 > lon:
        lon += res
    return lat, lon


def achar(texto):
    """O Plus Code dentro do texto (ou None)."""
    m = PADRAO.search(texto or "")
    if not m or m.group(1).index("+") % 2:
        return None  # antes do "+" o número de dígitos é sempre par
    return m.group(1)
