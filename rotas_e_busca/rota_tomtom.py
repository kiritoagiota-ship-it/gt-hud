"""Rotas que SABEM do trânsito de agora, da TomTom (Routing API v1, com a
chave gratuita do dono; pedido dele em 07/10/2026).

Duas coisas:
- pedir(): a rota mais rápida pelo trânsito deste momento. Entra na prévia
  como mais uma opção ("Pelo trânsito de agora"), ao lado da Rápida e da
  Tranquila (que continuam vindo do servidor de bike, sem trânsito).
- conferir(): durante a navegação, refaz na TomTom o caminho que a pessoa
  ESTÁ seguindo (seja qual for) e devolve quanto o trânsito atrasa esse
  caminho agora e se existe outro bem mais rápido.

A moto elétrica dele chega a ~50 km/h: a TomTom calcula para "carro que não
passa de VEL_MAX_KMH e não entra em rodovia" (o modo "motorcycle" dela ainda
é experimental). A TomTom não dá o relevo: a altimetria vem do mesmo servidor
das outras rotas (rota.elevacao_de).

Feito pela documentação (docs.tomtom.com/routing-api): cada parâmetro foi
conferido nela, mas a resposta de verdade só existe com a chave, no celular.
"""
import json
import urllib.parse

import rede
import rota as rotas

URL = "https://api.tomtom.com/routing/1/calculateRoute/%s/json?"
VEL_MAX_KMH = 50
PONTOS_APOIO_MAX = 160       # o caminho atual mandado para a TomTom refazer (reduzido a no máximo isso)
MESMO_CAMINHO = 0.12         # a TomTom "refez" com mais que isso de diferença no comprimento: não é o mesmo caminho
GANHO_MIN_S = 150            # só sugere outro caminho se economizar isso...
GANHO_MIN_FRACAO = 0.15      # ...e pelo menos esta fração do tempo que falta

# manobra da TomTom -> ação do app (as mesmas de rota._ACOES); None = não vira aviso
_ACOES = {
    "ARRIVE": "chegada", "ARRIVE_LEFT": "chegada_esquerda", "ARRIVE_RIGHT": "chegada_direita",
    "DEPART": "em_frente", "STRAIGHT": "em_frente",
    "KEEP_RIGHT": "mantenha_direita", "BEAR_RIGHT": "levemente_direita", "TURN_RIGHT": "direita",
    "SHARP_RIGHT": "acentuada_direita",
    "KEEP_LEFT": "mantenha_esquerda", "BEAR_LEFT": "levemente_esquerda", "TURN_LEFT": "esquerda",
    "SHARP_LEFT": "acentuada_esquerda",
    "MAKE_UTURN": "retorno", "TRY_MAKE_UTURN": "retorno",
    "ENTER_MOTORWAY": "em_frente", "ENTER_FREEWAY": "em_frente", "ENTER_HIGHWAY": "em_frente",
    "TAKE_EXIT": "saida_direita", "MOTORWAY_EXIT_LEFT": "saida_esquerda", "MOTORWAY_EXIT_RIGHT": "saida_direita",
    "ENTRANCE_RAMP": "saida_direita",
    "ROUNDABOUT_CROSS": "rotatoria", "ROUNDABOUT_RIGHT": "rotatoria", "ROUNDABOUT_LEFT": "rotatoria",
    "ROUNDABOUT_BACK": "rotatoria",
    "SWITCH_PARALLEL_ROAD": "em_frente", "SWITCH_MAIN_ROAD": "em_frente",
}


def _parametros(chave, rumo=None, **extra):
    p = [("key", chave), ("travelMode", "car"), ("traffic", "true"), ("routeType", "fastest"),
         ("vehicleMaxSpeed", str(VEL_MAX_KMH)), ("avoid", "motorways"), ("avoid", "unpavedRoads"),
         ("instructionsType", "text"), ("language", "pt-BR"), ("computeTravelTimeFor", "all")]
    if rumo is not None:
        p.append(("vehicleHeading", str(int(rumo) % 360)))
    p += [(k, str(v)) for k, v in extra.items()]
    return urllib.parse.urlencode(p)


def _lugares(origem, destino):
    return "%.6f,%.6f:%.6f,%.6f" % (origem[0], origem[1], destino[0], destino[1])


def _ler_rota(r, destino_nome="", com_relevo=True, elevacao_de=None):
    """Uma rota da resposta da TomTom -> rota.Rota (None se veio sem pontos)."""
    pontos = []
    for perna in r.get("legs") or []:
        for p in perna.get("points") or []:
            ponto = (p["latitude"], p["longitude"])
            if not pontos or pontos[-1] != ponto:
                pontos.append(ponto)
    if len(pontos) < 2:
        return None
    manobras = []
    for i in (r.get("guidance") or {}).get("instructions") or []:
        acao = _ACOES.get(i.get("maneuver"))
        if acao is None:
            continue
        manobras.append({"acao": acao, "indice": max(0, min(len(pontos) - 1, int(i.get("pointIndex") or 0))),
                         "texto": i.get("message") or "", "ruas": i.get("street") or "",
                         "saida": i.get("roundaboutExitNumber")})
    resumo = r.get("summary") or {}
    elevacao = []
    if com_relevo:
        try:
            elevacao = (elevacao_de or rotas.elevacao_de)(pontos)
        except Exception as e:   # sem o relevo a rota serve igual (só fica sem o gráfico e os avisos de subida)
            print("[rota] relevo da rota da TomTom:", type(e).__name__)
    rota = rotas.Rota(pontos, manobras, elevacao, float(resumo.get("travelTimeInSeconds") or 0.0), destino_nome)
    rota.perfil = "transito"
    rota.nome_perfil = "Pelo trânsito de agora"
    rota.tempo_com_transito = True       # o tempo dela JÁ considera o trânsito (não soma o atraso de novo)
    rota.sem_transito_s = float(resumo.get("noTrafficTravelTimeInSeconds") or 0.0)
    rota.atraso_tomtom_s = float(resumo.get("trafficDelayInSeconds") or 0.0)
    return rota


def pedir(chave, origem, destino, rumo=None, destino_nome="", baixar=None, elevacao_de=None):
    """A rota mais rápida pelo trânsito de agora. Chamada que espera a
    resposta (use rede.em_segundo_plano). None se a TomTom não achou caminho."""
    url = URL % _lugares(origem, destino) + _parametros(chave, rumo)
    dados = json.loads((baixar or rede.baixar)(url, 12).decode("utf-8"))
    achadas = dados.get("routes") or []
    return _ler_rota(achadas[0], destino_nome, elevacao_de=elevacao_de) if achadas else None


def _apoio(rota, dist_feita, posicao):
    """O que falta do caminho, em até PONTOS_APOIO_MAX pontos (o primeiro é
    onde a pessoa está; o último, o destino)."""
    ac = rota.acumulado
    i0 = next((i for i, d in enumerate(ac) if d > dist_feita), len(ac) - 1)
    resto = rota.pontos[i0:]
    passo = max(1, -(-len(resto) // PONTOS_APOIO_MAX))   # (divisão arredondada para cima)
    reduzido = resto[::passo]
    if not reduzido or reduzido[-1] != rota.pontos[-1]:
        reduzido.append(rota.pontos[-1])
    return [tuple(posicao)] + [p for p in reduzido if p != tuple(posicao)]


def conferir(chave, rota, dist_feita, posicao, rumo=None, enviar=None):
    """Como o trânsito de agora afeta o caminho que a pessoa está seguindo:
      {"atraso_s":   quanto o trânsito soma ao que falta (0 = livre),
       "falta_s":    o tempo que falta pelo relógio da TomTom,
       "melhor":     outra rota (rota.Rota) bem mais rápida, ou None,
       "ganho_s":    quanto ela economiza}
    None se a TomTom não conseguiu refazer o MESMO caminho (ex.: trecho por
    ciclovia, onde carro não passa): aí o app fica com o que já sabia."""
    apoio = _apoio(rota, dist_feita, posicao)
    if len(apoio) < 2:
        return None
    url = URL % _lugares(apoio[0], apoio[-1]) + _parametros(
        chave, rumo, maxAlternatives=1, alternativeType="betterRoute", minDeviationTime=GANHO_MIN_S)
    corpo = {"supportingPoints": [{"latitude": lat, "longitude": lon} for lat, lon in apoio]}
    dados = (enviar or rede.enviar)(url, corpo, "POST", 12)
    achadas = dados.get("routes") or []
    if not achadas:
        return None
    resumo = achadas[0].get("summary") or {}
    falta_m = max(1.0, rota.total_m - dist_feita)
    comprimento = float(resumo.get("lengthInMeters") or 0.0)
    if abs(comprimento - falta_m) > MESMO_CAMINHO * falta_m + 80:
        return None
    falta_s = float(resumo.get("travelTimeInSeconds") or 0.0)
    livre_s = float(resumo.get("noTrafficTravelTimeInSeconds") or falta_s)
    resposta = {"atraso_s": max(0.0, falta_s - livre_s), "falta_s": falta_s, "melhor": None, "ganho_s": 0.0}
    if len(achadas) > 1:
        outra = achadas[1].get("summary") or {}
        ganho = falta_s - float(outra.get("travelTimeInSeconds") or falta_s)
        if ganho >= GANHO_MIN_S and ganho >= GANHO_MIN_FRACAO * falta_s:
            melhor = _ler_rota(achadas[1], rota.destino_nome)
            if melhor is not None:
                resposta.update(melhor=melhor, ganho_s=ganho)
    return resposta
