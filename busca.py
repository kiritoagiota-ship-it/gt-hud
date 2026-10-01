"""Busca de lugares e endereços.

1) Google Places ("Text Search" novo): a mesma base que Google Maps e Uber
   usam (empresas pequenas, como barbearias, estão lá e não no mapa aberto).
   Só funciona com a chave do dono (chaves.py); a chave é travada para este
   app (pacote + certificado nos cabeçalhos X-Android-*) e o plano gratuito
   cobre 5.000 buscas por mês.
2) Sem chave, sem internet para o Google ou sem resultado lá: Photon (dados
   do OpenStreetMap, grátis, aceita nome aproximado).
A busca só roda quando a pessoa confirma (nada de buscar a cada letra).
"""
import urllib.parse

import chaves
import rede
from rota import distancia_m

GOOGLE = "https://places.googleapis.com/v1/places:searchText"
PHOTON = "https://photon.komoot.io/api/"
PACOTE = "org.kirito.gthud"
CERT_SHA1 = "4E22C21B14BD3A119E9737C9C7E378CCBD5F569D"   # parte pública do certificado do APK
RAIO_PREFERENCIA_M = 30000.0
LONGE_M = 200000.0
MAX_RESULTADOS = 8


def _google(texto, perto, chave):
    corpo = {"textQuery": texto, "languageCode": "pt-BR", "regionCode": "BR",
             "maxResultCount": MAX_RESULTADOS}
    if perto:
        corpo["locationBias"] = {"circle": {
            "center": {"latitude": perto[0], "longitude": perto[1]},
            "radius": RAIO_PREFERENCIA_M}}
    resposta = rede.enviar_json(GOOGLE, corpo, {
        "X-Goog-Api-Key": chave,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
        "X-Android-Package": PACOTE,
        "X-Android-Cert": CERT_SHA1,
    })
    lugares = []
    for p in resposta.get("places", []):
        local = p.get("location") or {}
        if "latitude" not in local:
            continue
        endereco = (p.get("formattedAddress") or "").replace(", Brasil", "").replace(", Brazil", "")
        lugares.append({"nome": (p.get("displayName") or {}).get("text") or endereco,
                        "endereco": endereco,
                        "lat": local["latitude"], "lon": local["longitude"]})
    return lugares


def _photon(texto, perto):
    params = {"q": texto, "limit": MAX_RESULTADOS}
    if perto:
        params.update(lat="%.5f" % perto[0], lon="%.5f" % perto[1])
    dados = rede.baixar_json(PHOTON + "?" + urllib.parse.urlencode(params))
    lugares = []
    for f in dados.get("features", []):
        pr = f.get("properties", {})
        lon, lat = f["geometry"]["coordinates"][:2]
        rua = " ".join(x for x in (pr.get("street"), pr.get("housenumber")) if x)
        partes = [x for x in (rua, pr.get("district"), pr.get("city"), pr.get("state")) if x]
        nome = pr.get("name") or rua or (partes[0] if partes else "Sem nome")
        lugares.append({"nome": nome, "endereco": ", ".join(p for p in partes if p != nome)[:90],
                        "lat": lat, "lon": lon})
    return lugares


def buscar(texto, perto=None):
    """Chamada que espera a resposta (use rede.em_segundo_plano).
    Devolve [{nome, endereco, lat, lon, dist_m, fonte}]."""
    lugares, fonte = [], "mapa aberto"
    chave = chaves.chave("google_places")
    if chave:
        try:
            lugares, fonte = _google(texto, perto, chave), "Google"
        except Exception as e:
            print("[busca] Google falhou, usando o mapa aberto:", e)
    if not lugares:
        lugares, fonte = _photon(texto, perto), "mapa aberto"
    for lugar in lugares:
        lugar["fonte"] = fonte
        lugar["dist_m"] = distancia_m(perto, (lugar["lat"], lugar["lon"])) if perto else None
    if perto and any(l["dist_m"] < LONGE_M for l in lugares):
        lugares = [l for l in lugares if l["dist_m"] < LONGE_M]  # "Bosque" de outro estado, não
    unicos = []
    for l in lugares:  # a mesma rua vem em vários pedaços: fica um só
        if not any(u["nome"] == l["nome"] and distancia_m((u["lat"], u["lon"]), (l["lat"], l["lon"])) < 1500
                   for u in unicos):
            unicos.append(l)
    return unicos
