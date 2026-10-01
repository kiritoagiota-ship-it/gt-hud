"""Busca de lugares e endereços (só em Goiânia: goiania.py).

Ordem:
1) Lugares SALVOS pela pessoa (segurar o dedo no mapa -> Salvar): resolve
   na hora quem não está em base nenhuma (ex.: a barbearia do amigo).
2) Base OFFLINE de Goiânia (dados/goiania_lugares.db, ~70 mil comércios e
   serviços da Overture Maps, gerada por ferramentas/gerar_goiania.py):
   grátis, sem internet, instantânea; acha por nome ou por tipo
   ("barbearia", "farmácia"...).
3) Endereço/rua (ou pouco resultado): Photon (OpenStreetMap), grátis, preso
   ao retângulo de Goiânia.
4) Google Places, SÓ se um dia houver chave (chaves.py; exige conta paga no
   Google Cloud, que o dono não tem por enquanto).
A busca só roda quando a pessoa confirma (nada de buscar a cada letra).
"""
import os
import re
import sqlite3
import unicodedata
import urllib.parse

import chaves
import goiania
import rede
from rota import distancia_m

GOOGLE = "https://places.googleapis.com/v1/places:searchText"
PHOTON = "https://photon.komoot.io/api/"
PACOTE = "org.kirito.gthud"
CERT_SHA1 = "4E22C21B14BD3A119E9737C9C7E378CCBD5F569D"   # parte pública do certificado do APK
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados", "goiania_lugares.db")
MAX_RESULTADOS = 12
POUCOS = 4                 # menos que isso na base offline: pergunta também ao Photon
_PALAVRAS_VAZIAS = {"e", "de", "da", "do", "das", "dos", "a", "o", "as", "os", "&", "-"}
_PARECE_ENDERECO = re.compile(r"\d|^(rua|r\.?|av\.?|avenida|alameda|al\.?|travessa|praca|rodovia|go-|br-)\b")


def normalizar(texto):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(t.lower().split())


def _termos(texto):
    return [t for t in normalizar(texto).split() if t not in _PALAVRAS_VAZIAS]


# --- 1) salvos -------------------------------------------------------------------
def _salvos(texto, salvos):
    termos = _termos(texto)
    achados = []
    for s in salvos:
        alvo = normalizar(s.get("nome", "") + " " + s.get("endereco", ""))
        if termos and all(t in alvo for t in termos):
            achados.append(dict(s, fonte="salvo", nota=100))
    return achados


# --- 2) base offline ---------------------------------------------------------------
def _offline(texto):
    termos = _termos(texto)
    if not termos or not os.path.exists(BASE):
        return []
    con = sqlite3.connect(BASE)
    try:
        linhas = con.execute(
            "SELECT nome, categoria, endereco, lat, lon, conf FROM lugares WHERE "
            + " AND ".join(["busca LIKE ?"] * len(termos)) + " LIMIT 400",
            ["%" + t + "%" for t in termos]).fetchall()
    finally:
        con.close()
    frase = " ".join(termos)
    lugares = []
    for nome, categoria, endereco, lat, lon, conf in linhas:
        n = " ".join(_termos(nome))  # sem "de/dos/e": "bosque dos buritis" = "bosque buritis"
        # nome igual/começando com o que foi digitado vale mais que achar só
        # pela categoria; "confiança" da Overture desempata
        nota = conf * 10
        if frase in n:
            nota += 30 + (20 if n.startswith(frase) else 0)
        elif all(t in n for t in termos):
            nota += 20
        detalhe = ", ".join(x for x in (categoria.capitalize() if categoria else "", endereco) if x)
        lugares.append({"nome": nome, "endereco": detalhe[:90], "lat": lat, "lon": lon,
                        "fonte": "Goiânia", "nota": nota})
    return lugares


# --- 3) Photon (endereços) -----------------------------------------------------------
def _photon(texto, perto):
    lat0, lon0, lat1, lon1 = goiania.LIMITES
    params = {"q": texto, "limit": MAX_RESULTADOS, "lang": "default",
              "bbox": "%s,%s,%s,%s" % (lon0, lat0, lon1, lat1)}
    if perto:
        params.update(lat="%.5f" % perto[0], lon="%.5f" % perto[1])
    dados = rede.baixar_json(PHOTON + "?" + urllib.parse.urlencode(params))
    lugares = []
    for f in dados.get("features", []):
        pr = f.get("properties", {})
        lon, lat = f["geometry"]["coordinates"][:2]
        if not goiania.dentro(lat, lon):
            continue
        rua = " ".join(x for x in (pr.get("street"), pr.get("housenumber")) if x)
        partes = [x for x in (rua, pr.get("district"), pr.get("city")) if x]
        nome = pr.get("name") or rua or (partes[0] if partes else "Sem nome")
        lugares.append({"nome": nome, "endereco": ", ".join(p for p in partes if p != nome)[:90],
                        "lat": lat, "lon": lon, "fonte": "mapa aberto", "nota": 15})
    return lugares


# --- 4) Google (só com chave) ----------------------------------------------------------
def _google(texto, perto, chave):
    corpo = {"textQuery": texto, "languageCode": "pt-BR", "regionCode": "BR",
             "maxResultCount": MAX_RESULTADOS}
    lat0, lon0, lat1, lon1 = goiania.LIMITES
    corpo["locationRestriction"] = {"rectangle": {
        "low": {"latitude": lat0, "longitude": lon0}, "high": {"latitude": lat1, "longitude": lon1}}}
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
                        "endereco": endereco, "lat": local["latitude"], "lon": local["longitude"],
                        "fonte": "Google", "nota": 40})
    return lugares


def buscar(texto, perto=None, salvos=()):
    """Chamada que espera a resposta (use rede.em_segundo_plano).
    Devolve [{nome, endereco, lat, lon, dist_m, fonte}], o melhor primeiro."""
    lugares = _salvos(texto, salvos) + _offline(texto)
    chave = chaves.chave("google_places")
    if chave:
        try:
            lugares += _google(texto, perto, chave)
        except Exception as e:
            print("[busca] Google falhou:", e)
    if len(lugares) < POUCOS or _PARECE_ENDERECO.search(normalizar(texto)):
        try:
            lugares += _photon(texto, perto)
        except Exception as e:  # sem internet: fica com o que já achou offline
            print("[busca] Photon falhou:", e)
            if not lugares:
                raise
    for lugar in lugares:
        lugar["dist_m"] = distancia_m(perto, (lugar["lat"], lugar["lon"])) if perto else None
    # melhor nota primeiro; entre parecidos, o mais perto (cada 1 km pesa 1 ponto)
    lugares.sort(key=lambda l: -(l["nota"] - (l["dist_m"] or 0) / 1000.0))
    unicos = []
    for l in lugares:  # o mesmo lugar vindo de duas fontes (ou a rua em vários pedaços)
        if not any(normalizar(u["nome"]) == normalizar(l["nome"])
                   and distancia_m((u["lat"], u["lon"]), (l["lat"], l["lon"])) < 300 for u in unicos):
            unicos.append(l)
    return unicos[:MAX_RESULTADOS]
