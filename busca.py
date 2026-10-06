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

Lugar que só o Google conhece (ex.: "Barbearia Imagem", que não está em
nenhuma base gratuita): colar aqui o que o Google Maps dá (lugar_colado):
- o PLUS CODE da página do lugar (ex.: "9MJH+9W"): ponto exato, sem internet;
- coordenadas ("-16.61906, -49.32019"): ponto exato;
- o LINK de Compartilhar: o link curto do app (maps.app.goo.gl) leva a uma
  página SEM coordenadas (testado com um link real em 01/10/2026), só nome
  e endereço; o app procura esse endereço no mapa aberto (aproximado: a
  rua). Link antigo/longo com "@lat,lon" ou "!3d..!4d.." é exato.
"""
import math
import os
import re
import sqlite3
import unicodedata
import urllib.parse

import chaves
import goiania
import pluscode
import rede
from rota import distancia_m

GOOGLE = "https://places.googleapis.com/v1/places:searchText"
PHOTON = "https://photon.komoot.io/api/"
PACOTE = "org.kirito.gthud"
CERT_SHA1 = "4E22C21B14BD3A119E9737C9C7E378CCBD5F569D"   # parte pública do certificado do APK
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados", "goiania_lugares.db")
MAX_RESULTADOS = 12
NOME_PERTO_M = 50          # ponto colado: sugere o nome do lugar conhecido até essa distância
POUCOS = 4                 # menos que isso na base offline: pergunta também ao Photon
_PALAVRAS_VAZIAS = {"e", "de", "da", "do", "das", "dos", "a", "o", "as", "os", "&", "-"}
_COORDENADAS = re.compile(r"(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})")
_PINO = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")          # o ponto do lugar
_CENTRO = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")            # o centro do mapa
_CONSULTA = re.compile(r"[?&](?:q|query|ll|destination)=(-?\d+\.\d+)(?:%2C|,)(-?\d+\.\d+)")
_NOME = re.compile(r"/maps/place/([^/@?]+)")
_PARECE_ENDERECO = re.compile(r"\d|^(rua|r\.?|av\.?|avenida|alameda|al\.?|travessa|praca|rodovia|go-|br-)\b")


def normalizar(texto):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(t.lower().split())


def _termos(texto):
    return [t for t in normalizar(texto).split() if t not in _PALAVRAS_VAZIAS]


# --- 0) link do Google Maps ou coordenadas coladas ---------------------------------
def _ponto_da_url(url):
    for padrao in (_PINO, _CONSULTA, _CENTRO):
        m = padrao.search(url)
        if m:
            return float(m.group(1)), float(m.group(2))
    return None


_ABREVIACOES = [(r"\bR\.", "Rua"), (r"\bAv\.", "Avenida"), (r"\bAl\.", "Alameda"),
                 (r"\bSt\.", "Setor"), (r"\bJd\.", "Jardim"), (r"\bPq\.", "Parque"),
                 (r"\bRes\.", "Residencial"), (r"\bVl\.", "Vila"), (r"\bTv\.", "Travessa")]
_PEDACO_INUTIL = re.compile(r"^(qd|quadra|lt|lote|n|nº|n°|sala|apto|casa|bloco|s/n|\d)|^\d{5}-?\d{3}$|^go$|^goi[aâ]nia$",
                            re.IGNORECASE)


def _do_endereco(nome_e_endereco, geocodificar=None):
    """ "BARBEARIA IMAGEM - R. do Sereno, quadra 141 - lote 20 - St. Morada do
    Sol, Goiânia - GO, 74475-211" -> (nome, endereço, ponto da RUA ou None)."""
    partes = [p.strip() for p in nome_e_endereco.split(" - ")]
    nome, resto = partes[0], " - ".join(partes[1:])
    pedacos = [p.strip() for p in re.split(r",| - ", resto) if p.strip()]
    uteis = []
    for p in pedacos:
        if not _PEDACO_INUTIL.search(p):
            for a, b in _ABREVIACOES:
                p = re.sub(a, b, p)
            uteis.append(p)
    consulta = ", ".join(uteis[:2] + ["Goiânia"])
    ponto = (geocodificar or _geocodificar_rua)(consulta) if uteis else None
    return nome[:60], resto, ponto


def _geocodificar_rua(consulta):
    lat0, lon0, lat1, lon1 = goiania.LIMITES
    dados = rede.baixar_json(PHOTON + "?" + urllib.parse.urlencode(
        {"q": consulta, "limit": 3, "bbox": "%s,%s,%s,%s" % (lon0, lat0, lon1, lat1)}))
    for f in dados.get("features", []):
        lon, lat = f["geometry"]["coordinates"][:2]
        if goiania.dentro(lat, lon):
            return lat, lon
    return None


def lugar_colado(texto, resolver=None, geocodificar=None):
    """Plus Code, "lat, lon" ou link do Google Maps -> lugar, ou None se o
    texto não é nada disso. resolver(url) -> url final (segue o link curto);
    geocodificar(endereço) -> (lat, lon) da rua. Os dois vão à internet."""
    texto = (texto or "").strip()
    link = next((p for p in texto.split() if p.startswith("http")), None)
    codigo = pluscode.achar(texto) if link is None else None
    if codigo is not None:
        lat, lon = pluscode.recuperar(codigo, *goiania.CENTRO)
        resto = texto.replace(codigo, "").strip(" ,")
        return {"nome": ("Plus Code " + codigo.upper()), "endereco": resto[:80] or "Plus Code do Google Maps",
                "lat": lat, "lon": lon, "sem_nome": True}
    if link is None:
        m = _COORDENADAS.search(texto)
        if m and not re.search(r"[a-zA-Z]{3,}", texto.replace(m.group(0), "")):
            lat, lon = float(m.group(1)), float(m.group(2))
            return {"nome": "Local colado", "endereco": "%.5f, %.5f" % (lat, lon), "lat": lat, "lon": lon,
                    "sem_nome": True}
        return None
    if "goo.gl" not in link and "google." not in link:
        return None
    ponto = _ponto_da_url(link)
    if ponto is None and "goo.gl" in link:
        link = (resolver or rede.url_final)(link)
        ponto = _ponto_da_url(link)
    m = _NOME.search(link)
    titulo = urllib.parse.unquote_plus(m.group(1)) if m else ""
    if ponto is not None:
        nome = titulo.split(" - ")[0][:60] if titulo else ""
        # o texto copiado do app do Google costuma vir "Nome do lugar\nhttps://..."
        antes = texto.split(link)[0].strip() if link in texto else ""
        achou = nome or (antes.splitlines()[-1][:60] if antes else "")
        lugar = {"nome": achou or "Lugar do Google Maps", "endereco": "do Google Maps",
                 "lat": ponto[0], "lon": ponto[1]}
        if not achou:
            lugar["sem_nome"] = True
        return lugar
    if not titulo:
        return None
    nome, endereco, ponto = _do_endereco(titulo, geocodificar)
    if ponto is None:
        return None
    return {"nome": nome, "endereco": "Aproximado (pela rua): " + endereco, "lat": ponto[0],
            "lon": ponto[1], "aproximado": True}


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
def nome_perto(lat, lon, raio_m=NOME_PERTO_M):
    """Nome do lugar conhecido (base offline) mais perto do ponto, até raio_m;
    "" se não há. Serve de sugestão de nome para um ponto colado ou marcado."""
    if not os.path.exists(BASE):
        return ""
    dlat = raio_m / 110540.0
    dlon = raio_m / (111320.0 * math.cos(math.radians(lat)))
    con = sqlite3.connect(BASE)
    try:
        linhas = con.execute(
            "SELECT nome, lat, lon FROM lugares WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
            (lat - dlat, lat + dlat, lon - dlon, lon + dlon)).fetchall()
    finally:
        con.close()
    perto = [(distancia_m((lat, lon), (la, lo)), nome) for nome, la, lo in linhas if nome]
    perto = [p for p in perto if p[0] <= raio_m]
    return min(perto)[1] if perto else ""


# --- lugares da base no MAPA (widgets/mapa.py) ---------------------------------------
CELULA_MAPA = 0.01      # graus (~1,1 km): o mapa pede os lugares por quadrado
MAX_POR_CELULA = 500
CONF_MAPA_MIN = 0.75    # abaixo disso a Overture não tem certeza de que o lugar existe
_GRUPOS = {
    "comida": "restaurante bar padaria pizzaria lanchonete hamburgueria sorveteria cafeteria café "
              "doceria sucos churrascaria",
    "saude": "dentista farmácia hospital consultório laboratório veterinário fisioterapia",
    "ensino": "escola faculdade creche autoescola",
    "servico": "imobiliária advogado contador banco órgão posto hotel pousada polícia gráfica oficina "
               "borracharia lava lavanderia salão barbearia cabeleireiro manicure estética spa tatuagem",
    "lazer": "igreja academia pilates luta",
    "praca": "parque",
}
_GRUPO_DA_CATEGORIA = {c: g for g, cs in _GRUPOS.items() for c in cs.split()}


def grupo_da_categoria(categoria):
    """Grupo (cor no mapa) da categoria da base; o que não está na lista e
    tem categoria é comércio; sem categoria, "outros"."""
    if not categoria:
        return "outros"
    return _GRUPO_DA_CATEGORIA.get(categoria, "compras")


def lugares_da_celula(cx, cy):
    """[(nome, categoria, lat, lon, confiança)] do quadrado (cx, cy) de
    CELULA_MAPA graus, os mais confiáveis primeiro. Use numa thread."""
    if not os.path.exists(BASE):
        return []
    con = sqlite3.connect(BASE)
    try:
        return con.execute(
            "SELECT nome, categoria, lat, lon, conf FROM lugares WHERE lat >= ? AND lat < ? AND lon >= ? "
            "AND lon < ? AND conf >= ? ORDER BY conf DESC LIMIT ?",
            (cx * CELULA_MAPA, (cx + 1) * CELULA_MAPA, cy * CELULA_MAPA, (cy + 1) * CELULA_MAPA,
             CONF_MAPA_MIN, MAX_POR_CELULA)).fetchall()
    finally:
        con.close()


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
    colado = lugar_colado(texto)
    if colado is not None:
        if colado.get("sem_nome"):
            # código/coordenada não traz nome: sugere o lugar conhecido ali
            colado["sugestao"] = nome_perto(colado["lat"], colado["lon"])
        colado.update(fonte="colado", nota=100,
                      dist_m=distancia_m(perto, (colado["lat"], colado["lon"])) if perto else None)
        return [colado]
    lugares = buscar_local(texto, None, salvos, ordenar=False)
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
    return _ordenar(lugares, perto)


def buscar_local(texto, perto=None, salvos=(), ordenar=True):
    """Só o que está no celular (lugares salvos + base offline): rápido e sem
    internet. É o que aparece ENQUANTO a pessoa digita."""
    lugares = _salvos(texto, salvos) + _offline(texto)
    return _ordenar(lugares, perto) if ordenar else lugares


def _ordenar(lugares, perto):
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
