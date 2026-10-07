"""Trânsito ao vivo (escolhido pelo dono em 08/10/2026): acidentes, trânsito
lento, obras e vias interditadas, da TomTom (Traffic API, "Incident
Details" v5).

A TomTom tem um plano gratuito (2.500 consultas por dia, sem cartão; acima
disso ela bloqueia, não cobra). A CHAVE é do dono: ele cria a conta, cola
a chave nos Ajustes do app e ela fica só no celular (nunca no código, que é
público, nem nos registros de diagnóstico).

Uma consulta traz as ocorrências de Goiânia INTEIRA (a área cabe no limite
da TomTom); o app guarda por VALIDADE_S e usa para qualquer rota. Para cada
rota, vê quais ocorrências ficam em cima do caminho e no MESMO sentido.

Limites: a TomTom mede bem avenidas e vias grandes; rua de bairro quase não
aparece. E o atraso que ela informa é para carro: moto e bike passam melhor
(ATRASO_MOTO).
"""
import json
import time
import urllib.error
import urllib.parse

import goiania
import rede
from rota import _dist_segmento, distancia_m

URL = "https://api.tomtom.com/traffic/services/5/incidentDetails"
CAMPOS = ("{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,"
          "events{description,code,iconCategory},from,to,length,delay,probabilityOfOccurrence}}}")
VALIDADE_S = 180.0       # as ocorrências da cidade valem por isso (não gasta consulta à toa)
NA_ROTA_M = 28.0         # até isso da linha da rota: está no caminho
ATRASO_MOTO = 0.6        # do atraso informado (para carro), quanto vale para a moto elétrica
# categoria da TomTom -> (nome para a tela, nome para a fala)
CATEGORIAS = {
    1: ("Acidente", "acidente"), 3: ("Perigo na via", "perigo na via"), 6: ("Trânsito lento", "trânsito lento"),
    7: ("Faixa fechada", "faixa fechada"), 8: ("Via interditada", "via interditada"),
    9: ("Obras", "obras"), 11: ("Alagamento", "alagamento"), 14: ("Veículo quebrado", "veículo quebrado"),
}
INTERDITADA = 8

_guardado = None         # (hora, [ocorrências])


class SemChave(Exception):
    """A TomTom recusou a chave (errada, apagada ou sem o produto de trânsito)."""


def _ler(resposta):
    ocorrencias = []
    for item in resposta.get("incidents") or []:
        p = item.get("properties") or {}
        g = item.get("geometry") or {}
        categoria = p.get("iconCategory") or 0
        if categoria not in CATEGORIAS or p.get("probabilityOfOccurrence") in ("improbable", "risk_of"):
            continue
        coordenadas = g.get("coordinates") or []
        if g.get("type") == "Point":
            coordenadas = [coordenadas]
        pontos = [(c[1], c[0]) for c in coordenadas if isinstance(c, (list, tuple)) and len(c) >= 2]
        if not pontos:
            continue
        descricao = "; ".join(e.get("description") or "" for e in (p.get("events") or []) if e.get("description"))
        ocorrencias.append({
            "categoria": categoria, "magnitude": p.get("magnitudeOfDelay") or 0,
            "atraso_s": float(p.get("delay") or 0.0), "metros": float(p.get("length") or 0.0),
            "descricao": descricao[:120], "de": p.get("from") or "", "ate": p.get("to") or "",
            "pontos": pontos})
    return ocorrencias


def buscar(chave, caixa=None, baixar=None):
    """Ocorrências na caixa (lat0, lon0, lat1, lon1; padrão: Goiânia inteira).
    Chamada que espera a resposta (use rede.em_segundo_plano)."""
    lat0, lon0, lat1, lon1 = caixa or goiania.LIMITES
    consulta = urllib.parse.urlencode({
        "key": chave, "bbox": "%.5f,%.5f,%.5f,%.5f" % (lon0, lat0, lon1, lat1),
        "fields": CAMPOS, "language": "pt-BR", "timeValidityFilter": "present"})
    try:
        dados = (baixar or rede.baixar)(URL + "?" + consulta, 12)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SemChave("A TomTom recusou a chave.")
        raise
    return _ler(json.loads(dados.decode("utf-8") if isinstance(dados, bytes) else dados))


def da_cidade(chave, agora=None, baixar=None):
    """As ocorrências de Goiânia, de no máximo VALIDADE_S atrás."""
    global _guardado
    agora = time.monotonic() if agora is None else agora
    if _guardado is not None and 0 <= agora - _guardado[0] < VALIDADE_S:
        return _guardado[1]
    ocorrencias = buscar(chave, baixar=baixar)
    _guardado = (agora, ocorrencias)
    return ocorrencias


def esquecer():
    global _guardado
    _guardado = None


def testar(chave):
    """None se a chave funciona; senão, o texto do problema."""
    try:
        buscar(chave)
        return None
    except SemChave:
        return ("A TomTom recusou essa chave. Confira se copiou inteira e se o produto "
                "\"Traffic API\" está ligado nela.")
    except Exception:
        return "Não consegui falar com a TomTom: confira a internet."


def _na_rota(rota, ponto, perto_de):
    """(metros desde o começo, distância até a linha) do ponto mais perto da
    rota, procurando em volta do índice `perto_de`."""
    pts, ac = rota.pontos, rota.acumulado
    melhor = (float("inf"), 0.0, perto_de)
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        d = _dist_segmento(ponto, a, b)
        if d < melhor[0]:
            trecho = ac[i + 1] - ac[i]
            f = min(1.0, distancia_m(a, ponto) / trecho) if trecho > 0 else 0.0
            melhor = (d, ac[i] + f * trecho, i)
    return melhor[1], melhor[0]


def na_rota(rota, ocorrencias):
    """As ocorrências que ficam EM CIMA da rota e no sentido dela:
    [{"inicio_m", "fim_m", "categoria", "magnitude", "atraso_s", "descricao"}],
    da mais próxima do começo para a mais distante."""
    if len(rota.pontos) < 2:
        return []
    lats = [p[0] for p in rota.pontos]
    lons = [p[1] for p in rota.pontos]
    folga = 0.0006
    caixa = (min(lats) - folga, min(lons) - folga, max(lats) + folga, max(lons) + folga)
    achadas = []
    for o in ocorrencias:
        pontos = o["pontos"]
        if not any(caixa[0] <= la <= caixa[2] and caixa[1] <= lo <= caixa[3] for la, lo in pontos):
            continue
        # até 12 pontos da ocorrência, por igual
        passo = max(1, len(pontos) // 12)
        amostra = pontos[::passo] + ([pontos[-1]] if (len(pontos) - 1) % passo else [])
        proximos = []
        for ponto in amostra:
            metros, longe = _na_rota(rota, ponto, 0)
            if longe <= NA_ROTA_M:
                proximos.append(metros)
        if not proximos:
            continue
        linha = len(amostra) >= 2
        if linha:
            if len(proximos) < max(2, len(amostra) * 0.4):
                continue                      # só encosta/cruza a rota: não é o caminho dele
            if proximos[-1] < proximos[0] - 20:
                continue                      # sentido contrário (a outra pista)
        inicio, fim = min(proximos), max(proximos)
        parte = min(1.0, (fim - inicio) / o["metros"]) if (linha and o["metros"] > 0) else 1.0
        achadas.append({"inicio_m": inicio, "fim_m": fim, "categoria": o["categoria"],
                        "magnitude": o["magnitude"], "atraso_s": o["atraso_s"] * parte * ATRASO_MOTO,
                        "descricao": o["descricao"]})
    achadas.sort(key=lambda a: a["inicio_m"])
    return achadas


def avaliar(rota, ocorrencias):
    """Guarda na rota o trânsito dela: rota.incidentes, rota.atraso_transito_s,
    rota.interditada e rota.trechos_transito [(pontos, magnitude)] para pintar."""
    achadas = na_rota(rota, ocorrencias)
    rota.incidentes = achadas
    rota.atraso_transito_s = sum(a["atraso_s"] for a in achadas)
    rota.interditada = any(a["categoria"] == INTERDITADA for a in achadas)
    pintar = []
    for a in achadas:
        if a["fim_m"] - a["inicio_m"] < 30:
            continue
        pontos, d = [], a["inicio_m"]
        while d < a["fim_m"]:
            pontos.append(rota.ponto_em(d)[:2])
            d += 25.0
        pontos.append(rota.ponto_em(a["fim_m"])[:2])
        pintar.append((pontos, 4 if a["categoria"] == INTERDITADA else max(1, a["magnitude"])))
    rota.trechos_transito = pintar
    return achadas


def resumo(rota):
    """Texto curto do trânsito da rota para a prévia ("" se está livre)."""
    achadas = getattr(rota, "incidentes", None) or []
    if not achadas:
        return ""
    partes = []
    if rota.interditada:
        partes.append("via interditada no caminho")
    minutos = int(round(rota.atraso_transito_s / 60.0))
    if minutos >= 1:
        partes.append("+%d min de trânsito" % minutos)
    outros = [CATEGORIAS[a["categoria"]][1] for a in achadas if a["categoria"] not in (6, INTERDITADA)]
    if outros:
        partes.append(outros[0] if len(outros) == 1 else "%d ocorrências" % len(outros))
    if not partes:
        partes.append("trânsito lento")
    texto = ", ".join(partes)
    return texto[:1].upper() + texto[1:]
