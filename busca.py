"""Busca de endereço/lugar (Nominatim do OpenStreetMap, grátis, sem conta).

Regras do Nominatim: no máximo 1 busca por segundo e nada de "autocompletar"
enquanto digita; por isso a busca só roda quando a pessoa confirma.
"""
import time
import urllib.parse

import rede
from rota import distancia_m

NOMINATIM = "https://nominatim.openstreetmap.org/search"
RAIO_PREFERENCIA_GRAUS = 0.35   # ~40 km: resultados perto de quem busca vêm primeiro

_ultima = [0.0]


def buscar(texto, perto=None):
    """Chamada que espera a resposta (use rede.em_segundo_plano).
    Devolve [{nome, endereco, lat, lon, dist_m}]."""
    espera = 1.1 - (time.time() - _ultima[0])
    if espera > 0:
        time.sleep(espera)
    _ultima[0] = time.time()
    params = {"q": texto, "format": "jsonv2", "limit": 8, "addressdetails": 0,
              "accept-language": "pt-BR", "countrycodes": "br"}
    if perto:
        lat, lon = perto
        r = RAIO_PREFERENCIA_GRAUS
        params["viewbox"] = "%.5f,%.5f,%.5f,%.5f" % (lon - r, lat + r, lon + r, lat - r)
    dados = rede.baixar_json(NOMINATIM + "?" + urllib.parse.urlencode(params))
    resultados = []
    for item in dados:
        partes = [p.strip() for p in item.get("display_name", "").split(",")]
        nome = item.get("name") or (partes[0] if partes else "Sem nome")
        resto = [p for p in partes if p and p != nome]
        lat, lon = float(item["lat"]), float(item["lon"])
        resultados.append({
            "nome": nome,
            "endereco": ", ".join(resto[:3]),
            "lat": lat, "lon": lon,
            "dist_m": distancia_m(perto, (lat, lon)) if perto else None,
        })
    if perto:
        resultados.sort(key=lambda r: r["dist_m"])
    return resultados
