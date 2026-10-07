"""Rota de bike: pede ao Valhalla do OpenStreetMap (grátis, sem conta), lê
as manobras e acha as subidas pela altimetria da rota.

Perfil escolhido pelo dono: caminho mais rápido (sem evitar subida nem
avenida). O Valhalla devolve também a elevação a cada ELEVACAO_PASSO_M ao
longo da rota; é dela que saem as subidas.
"""
import json
import math
import time
import urllib.error
import urllib.parse

import rede


class SemRota(Exception):
    """O servidor respondeu, mas não há caminho de bike até lá (não é falta
    de internet)."""

VALHALLA = "https://valhalla1.openstreetmap.de/route"
# Reserva (o principal é gratuito e às vezes recusa ou cai; sem ele o app
# não recalculava no meio do caminho): OSRM de bicicleta, em outros
# servidores. Não dá a altimetria (rota sem aviso de subida) nem perfis.
RESERVA = "https://routing.openstreetmap.de/routed-bike/route/v1/driving/"
RESERVA_TEMPO = 0.65    # o OSRM calcula a ~15 km/h; medido: o principal (elétrica) dá ~65% desse tempo
ESPERA_PRINCIPAL_S = 12
# multiplica o tempo de toda rota: o ritmo real do dono (ver ritmo.py)
fator_ritmo = 1.0
ELEVACAO_PASSO_M = 30
# subida que merece aviso: inclinação média >= SUBIDA_GRAU_MIN em pelo menos
# SUBIDA_COMPR_MIN_M, ganhando SUBIDA_GANHO_MIN_M ou mais de altura
SUBIDA_GRAU_MIN = 3.0
SUBIDA_COMPR_MIN_M = 60
SUBIDA_GANHO_MIN_M = 4.0
SUBIDA_EMENDA_M = 45   # subidas separadas por menos que isso viram uma só

# tipos de manobra do Valhalla -> ação usada no painel e na voz
_ACOES = {
    1: "em_frente", 2: "direita", 3: "esquerda",
    4: "chegada", 5: "chegada_direita", 6: "chegada_esquerda",
    7: "em_frente", 8: "em_frente",
    9: "levemente_direita", 10: "direita", 11: "acentuada_direita",
    12: "retorno", 13: "retorno", 14: "acentuada_esquerda", 15: "esquerda",
    16: "levemente_esquerda", 17: "em_frente", 18: "saida_direita", 19: "saida_esquerda",
    20: "saida_direita", 21: "saida_esquerda", 22: "em_frente",
    23: "mantenha_direita", 24: "mantenha_esquerda", 25: "em_frente",
    26: "rotatoria", 27: "sair_rotatoria", 37: "mantenha_direita", 38: "mantenha_esquerda",
}


def distancia_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371000.0 * math.asin(math.sqrt(h))


def decodificar_polyline(texto, precisao=1e6):
    """Formato "polyline6" do Valhalla -> [(lat, lon), ...]."""
    pontos, i, lat, lon = [], 0, 0, 0
    while i < len(texto):
        valores = []
        for _ in range(2):
            resultado = deslocamento = 0
            while True:
                b = ord(texto[i]) - 63
                i += 1
                resultado |= (b & 0x1F) << deslocamento
                deslocamento += 5
                if b < 0x20:
                    break
            valores.append(~(resultado >> 1) if resultado & 1 else resultado >> 1)
        lat += valores[0]
        lon += valores[1]
        pontos.append((lat / precisao, lon / precisao))
    return pontos


def codificar_polyline(pontos, precisao=1e6):
    """[(lat, lon), ...] -> texto "polyline" (o contrário de decodificar_polyline)."""
    saida, ult = [], (0, 0)
    for lat, lon in pontos:
        atual = (int(round(lat * precisao)), int(round(lon * precisao)))
        for v in (atual[0] - ult[0], atual[1] - ult[1]):
            v = ~(v << 1) if v < 0 else v << 1
            while v >= 0x20:
                saida.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            saida.append(chr(v + 63))
        ult = atual
    return "".join(saida)


def achar_subidas(elevacao, passo=ELEVACAO_PASSO_M):
    """[{inicio_m, fim_m, ganho_m, grau}] a partir da elevação a cada `passo` m."""
    if len(elevacao) < 3:
        return []
    # média de 3 amostras: o modelo de relevo tem degraus de ~1 m
    e = ([elevacao[0]]
         + [(elevacao[i - 1] + elevacao[i] + elevacao[i + 1]) / 3.0
            for i in range(1, len(elevacao) - 1)]
         + [elevacao[-1]])
    trechos, inicio = [], None
    for i in range(1, len(e)):
        subindo = (e[i] - e[i - 1]) / passo * 100.0 >= SUBIDA_GRAU_MIN
        if subindo and inicio is None:
            inicio = i - 1
        elif not subindo and inicio is not None:
            trechos.append([inicio, i - 1])
            inicio = None
    if inicio is not None:
        trechos.append([inicio, len(e) - 1])
    emendados = []
    for t in trechos:
        if emendados and (t[0] - emendados[-1][1]) * passo < SUBIDA_EMENDA_M:
            emendados[-1][1] = t[1]
        else:
            emendados.append(t)
    subidas = []
    for a, b in emendados:
        compr = (b - a) * passo
        ganho = e[b] - e[a]
        if compr >= SUBIDA_COMPR_MIN_M and ganho >= SUBIDA_GANHO_MIN_M:
            subidas.append({"inicio_m": a * passo, "fim_m": b * passo,
                            "ganho_m": ganho, "grau": ganho / compr * 100.0})
    return subidas


# Rotas que a pessoa pode escolher (pedido do dono: mais reta, mais dentro
# das vias, mais tranquila...). Opções do custo "bicycle" do Valhalla:
#   use_roads: 0 = foge de avenidas (ciclovia/rua calma), 1 = não se importa
#   use_hills: 0 = foge de subida, 1 = não se importa
#   shortest:  a menor distância, ignorando o resto
PERFIS = [
    ("rapida", "Mais rápida", {"use_roads": 0.75, "use_hills": 0.5, "avoid_bad_surfaces": 0.25}),
    ("tranquila", "Mais tranquila", {"use_roads": 0.0, "use_hills": 0.5, "avoid_bad_surfaces": 0.5}),
    ("plana", "Menos subida", {"use_roads": 0.5, "use_hills": 0.0, "avoid_bad_surfaces": 0.25}),
]
# ROTA TRANQUILA (pedido do dono, 06/10/2026: a moto elétrica dele chega a
# ~50 km/h e ele quer sempre uma opção por ruas calmas, longe das avenidas).
# Só pedir "use_roads: 0" ao servidor NÃO basta: medido em rotas reais de
# Goiânia, às vezes volta a mesma rota da "rápida" (71% em avenida). O que
# funciona: pedir também as rotas alternativas, MEDIR em cada uma quanto do
# caminho é em via movimentada (o servidor diz a classe de cada trecho) e
# ficar com a mais calma que não seja absurda de longa.
ATRIBUTOS = "https://valhalla1.openstreetmap.de/trace_attributes"
ALTURA = "https://valhalla1.openstreetmap.de/height"
MOVIMENTADAS = ("motorway", "trunk", "primary", "secondary")   # avenidas e vias expressas
ESPERA_ENTRE_S = 1.1          # o servidor gratuito aceita ~1 pedido por segundo
TRANQUILA_MAIS_LONGA = 1.6    # a tranquila pode levar até isso (x o tempo da rápida) + 3 min
TRANQUILA_GANHO = 0.08        # só é "tranquila" se tiver pelo menos isso a menos de avenida
NOMES_PERFIS = {p[0]: p[1] for p in PERFIS}


def elevacao_de(pontos, enviar=None):
    """A altitude (m) a cada ELEVACAO_PASSO_M ao longo de um caminho que não
    veio do servidor de bike (ex.: a rota da TomTom, que não traz o relevo)."""
    corpo = {"range": False, "encoded_polyline": codificar_polyline(pontos, 1e6),
             "shape_format": "polyline6", "resample_distance": ELEVACAO_PASSO_M}
    dados = (enviar or rede.enviar)(ALTURA, corpo, "POST", ESPERA_PRINCIPAL_S)
    return [float(h) for h in dados.get("height") or [] if h is not None]


class Rota:
    perfil = "rapida"
    nome_perfil = "Mais rápida"
    tempo_com_transito = False   # True: tempo_base_s já considera o trânsito de agora (rota_tomtom.py)

    def __init__(self, pontos, manobras, elevacao, tempo_s, destino_nome=""):
        self.pontos = pontos
        self.acumulado = [0.0]
        for a, b in zip(pontos, pontos[1:]):
            self.acumulado.append(self.acumulado[-1] + distancia_m(a, b))
        self.total_m = self.acumulado[-1]
        self.tempo_base_s = tempo_s      # o que o servidor previu
        self.reserva = False             # True: veio do servidor reserva
        self.movimentada = None          # fração (0..1) em avenida/via expressa; None = não medida
        self.estresse = None             # média dos níveis de estresse (medir_movimento)
        self.trechos = []                # [(pontos, nível)] das avenidas da rota
        self.avenidas = []               # [(início m, fim m, nível, nome)]
        # o que o app sabe a mais sobre ela (main.GTHudApp._informar_rotas):
        self.tempo_pessoal_s = None      # pelo histórico do dono (aprendizado.py); None = não conhece o caminho
        self.lentos = []                 # [(início m, fim m)] que costumam estar lentos neste horário
        self.extra_lento_s = 0.0
        self.atraso_transito_s = 0.0     # trânsito de agora (transito.py)
        self.incidentes = []             # acidentes, trânsito lento, obras... em cima da rota
        self.interditada = False
        self.trechos_transito = []       # [(pontos, magnitude)] para pintar no mapa
        self.destino_nome = destino_nome
        self.elevacao = elevacao
        self.subidas = achar_subidas(elevacao)
        # descida = "subida" da altimetria ao contrário (grau positivo = % de descida)
        self.descidas = achar_subidas([-e for e in elevacao])
        self.subida_total_m = sum(max(0.0, b - a) for a, b in zip(elevacao, elevacao[1:]))
        for m in manobras:
            m["dist_m"] = self.acumulado[min(m["indice"], len(self.acumulado) - 1)]
        self.manobras = manobras

    @property
    def tempo_s(self):
        """Tempo previsto: pelo histórico dele nos trechos que já conhece (ou o
        do servidor no ritmo dele), mais o atraso do trânsito de agora."""
        if self.tempo_com_transito:   # calculada pela TomTom com o trânsito deste momento
            return self.tempo_base_s
        base = self.tempo_pessoal_s if self.tempo_pessoal_s is not None else self.tempo_base_s * fator_ritmo
        return base + self.atraso_transito_s

    @classmethod
    def do_osrm(cls, dados, destino_nome=""):
        r = dados["routes"][0]
        pontos = decodificar_polyline(r["geometry"])
        manobras, indice = [], 0
        for passo in r["legs"][0]["steps"]:
            m = passo["maneuver"]
            acao = _acao_osrm(m.get("type"), m.get("modifier"))
            if acao is not None:
                manobras.append({"acao": acao, "indice": min(indice, len(pontos) - 1), "texto": "",
                                 "ruas": passo.get("name") or "", "saida": m.get("exit")})
            indice += max(0, len(decodificar_polyline(passo.get("geometry") or "")) - 1)
        rota = cls(pontos, manobras, [], r.get("duration", 0) * RESERVA_TEMPO, destino_nome)
        rota.reserva = True
        return rota

    @classmethod
    def do_valhalla(cls, dados, destino_nome=""):
        trecho = dados["trip"]["legs"][0]
        pontos = decodificar_polyline(trecho["shape"])
        manobras = []
        for m in trecho["maneuvers"]:
            manobras.append({
                "acao": _ACOES.get(m.get("type"), "em_frente"),
                "indice": m.get("begin_shape_index", 0),
                "texto": m.get("instruction", ""),
                "ruas": ", ".join(m.get("street_names") or []),
                "saida": m.get("roundabout_exit_count"),
            })
        return cls(pontos, manobras, trecho.get("elevation") or [],
                   dados["trip"]["summary"].get("time", 0), destino_nome)

    def ponto_em(self, dist_m, perto_de=0):
        """(lat, lon, rumo em graus) no ponto da rota a dist_m do começo;
        `perto_de` = índice de onde começar a procurar (a seta anda pouco)."""
        ac, pts = self.acumulado, self.pontos
        d = max(0.0, min(self.total_m, dist_m))
        i = max(0, min(perto_de, len(pts) - 2))
        while i > 0 and ac[i] > d:
            i -= 1
        while i < len(pts) - 2 and ac[i + 1] < d:
            i += 1
        a, b = pts[i], pts[i + 1]
        comp = ac[i + 1] - ac[i]
        f = (d - ac[i]) / comp if comp > 0 else 0.0
        rumo = math.degrees(math.atan2((b[1] - a[1]) * math.cos(math.radians(a[0])),
                                       b[0] - a[0])) % 360.0
        return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, rumo

    def subida_restante_m(self, dist_feita):
        """Quanto ainda falta subir a partir de dist_feita (soma das subidas)."""
        i0 = int(dist_feita // ELEVACAO_PASSO_M)
        e = self.elevacao
        return sum(max(0.0, e[i + 1] - e[i]) for i in range(max(0, i0), len(e) - 1))


_LADO_OSRM = {"right": "direita", "left": "esquerda", "slight right": "levemente_direita",
              "slight left": "levemente_esquerda", "sharp right": "acentuada_direita",
              "sharp left": "acentuada_esquerda", "uturn": "retorno", "straight": "em_frente"}


def _acao_osrm(tipo, lado):
    """Manobra do OSRM -> ação do app; None = não vale um aviso."""
    if tipo == "depart":
        return "em_frente"
    if tipo == "arrive":
        return {"right": "chegada_direita", "left": "chegada_esquerda"}.get(lado, "chegada")
    if tipo in ("roundabout", "rotary"):
        return "rotatoria"
    if tipo in ("exit roundabout", "exit rotary"):
        return "sair_rotatoria"
    if tipo == "fork":
        return "mantenha_esquerda" if "left" in (lado or "") else "mantenha_direita"
    if tipo in ("on ramp", "off ramp"):
        return "saida_esquerda" if "left" in (lado or "") else "saida_direita"
    if tipo in ("new name", "merge", "notification") or lado in (None, "straight"):
        return None  # a rua só mudou de nome / segue reto
    return _LADO_OSRM.get(lado)


def _pedir_reserva(origem, destino, destino_nome):
    url = RESERVA + "%.6f,%.6f;%.6f,%.6f?steps=true&geometries=polyline6&overview=full" % (
        origem[1], origem[0], destino[1], destino[0])
    try:
        dados = rede.baixar_json(url, timeout=20)
    except urllib.error.HTTPError as e:
        if e.code == 400:
            raise SemRota("Não achei um caminho de bike até esse lugar.")
        raise
    if dados.get("code") != "Ok" or not dados.get("routes"):
        raise SemRota("Não achei um caminho de bike até esse lugar.")
    return Rota.do_osrm(dados, destino_nome)


# Nível de estresse de cada trecho, inspirado no "Level of Traffic Stress"
# (LTS, o método usado no planejamento de ciclovias: classe da via, número de
# faixas, limite de velocidade e se há ciclovia), adaptado para a moto
# elétrica do dono (~50 km/h: acompanha o trânsito de rua e de avenida
# pequena; o perigo é via larga e rápida):
#   0 calmo      rua de bairro, via de serviço, ciclovia separada
#   1 moderado   coletora (terciária); avenida pequena de 1 faixa
#   2 movimentado avenida de 2 faixas ou 50 km/h; via principal de 1 faixa
#   3 pesado     via principal de 2+ faixas ou 60+ km/h; via expressa
PESO_NIVEL = (0.0, 1.0, 3.0, 6.0)   # quanto cada km de cada nível "custa" no estresse da rota
NIVEL_AVENIDA = 2                   # a partir daqui conta como "avenida" (o % mostrado e o desenho)
EVITAR_TRECHO_KM = 0.25             # trecho de avenida maior que isso entra na lista de "evitar"
EVITAR_MAX = 14                     # pontos de "evitar" por pedido
EVITAR_VOLTAS = 2                   # quantas vezes tenta contornar as avenidas achadas


def nivel_do_trecho(trecho):
    classe = trecho.get("road_class")
    faixas = trecho.get("lane_count") or 1
    limite = trecho.get("speed_limit") or 0
    if trecho.get("cycle_lane") in ("separated", "dedicated") or trecho.get("use") in (
            "cycleway", "path", "footway", "living_street"):
        return 0
    if classe in ("motorway", "trunk"):
        return 3
    if classe == "primary":
        return 3 if (faixas >= 2 or limite >= 60) else 2
    if classe == "secondary":
        if faixas >= 3 or limite >= 60:
            return 3
        return 2 if (faixas >= 2 or limite >= 50) else 1
    if classe == "tertiary":
        return 2 if (faixas >= 3 or limite >= 60) else 1
    return 0


def medir_movimento(rota):
    """Mede a rota trecho a trecho (o servidor diz classe, faixas e limite de
    cada um) e guarda nela:
      rota.movimentada  fração (0..1) do caminho em avenida (nível 2 ou 3)
      rota.estresse     média dos níveis pesada por PESO_NIVEL (menor = mais calma)
      rota.trechos      [(pontos, nível)] das avenidas, para desenhar no mapa
      rota.avenidas     [(início m, fim m, nível, nome)] ao longo da rota
    Devolve rota.movimentada, ou None se não deu para medir."""
    if rota.movimentada is not None:
        return rota.movimentada
    corpo = {"encoded_polyline": codificar_polyline(rota.pontos, 1e6), "costing": "bicycle",
             "shape_match": "map_snap",
             "filters": {"attributes": ["edge.road_class", "edge.length", "edge.lane_count", "edge.speed_limit",
                                        "edge.cycle_lane", "edge.use", "edge.begin_shape_index",
                                        "edge.end_shape_index", "edge.names", "shape"], "action": "include"}}
    try:
        dados = rede.enviar(ATRIBUTOS, corpo, "POST", ESPERA_PRINCIPAL_S)
    except Exception as e:
        print("[rota] nao deu para medir as avenidas:", e)
        return None
    forma = decodificar_polyline(dados.get("shape") or "") or rota.pontos
    alinhada = len(forma) == len(rota.pontos)   # mesmos pontos da rota: dá para saber a distância de cada trecho
    km = [0.0, 0.0, 0.0, 0.0]
    juntos = []    # [i0, i1, nível, nome, km] de avenidas, emendando trechos seguidos
    for trecho in dados.get("edges", []):
        n = nivel_do_trecho(trecho)
        comprimento = trecho.get("length") or 0.0
        km[n] += comprimento
        if n < NIVEL_AVENIDA:
            continue
        i0, i1 = trecho.get("begin_shape_index", 0), trecho.get("end_shape_index", 0)
        nome = (trecho.get("names") or [""])[0]
        if juntos and juntos[-1][1] == i0:
            juntos[-1][1] = i1
            juntos[-1][2] = max(juntos[-1][2], n)
            juntos[-1][3] = juntos[-1][3] or nome
            juntos[-1][4] += comprimento
        else:
            juntos.append([i0, i1, n, nome, comprimento])
    total = sum(km)
    if total <= 0:
        return None
    rota.estresse = sum(PESO_NIVEL[n] * v for n, v in enumerate(km)) / total
    rota.trechos = [(forma[i0:i1 + 1], n) for i0, i1, n, _, _ in juntos if i1 > i0]
    rota._evitar = [(forma[(i0 + i1) // 2], c) for i0, i1, _, _, c in juntos if c >= EVITAR_TRECHO_KM]
    if alinhada:
        rota.avenidas = [(rota.acumulado[i0], rota.acumulado[i1], n, nome) for i0, i1, n, nome, _ in juntos
                         if i1 < len(rota.acumulado)]
    rota.movimentada = (km[2] + km[3]) / total
    return rota.movimentada


def mais_tranquila(origem, destino, rumo=None, destino_nome="", rapida=None, esperar=time.sleep,
                   voltas=EVITAR_VOLTAS, ao_melhorar=None):
    """A rota mais calma até o destino. Como (testado em trajetos reais de
    Goiânia: a parte em avenida caiu de 91% para 3%, de 44% para 16% e de 28%
    para 8%, com 1 a 8 min a mais):
      1. mede a `rapida`;
      2. pede a rota "sem avenida" e as alternativas dela, e mede cada uma;
      3. manda o servidor EVITAR os trechos de avenida de todas as rotas vistas
         (a ideia dos pontos "nogo" do BRouter) e mede o que voltar; repete;
      4. fica com a de menor estresse que não passe de TRANQUILA_MAIS_LONGA
         vezes o tempo da rápida.
    A busca toda leva uns 12 a 17 s (o servidor gratuito aceita ~1 pedido por
    segundo): `ao_melhorar(rota)` é chamado a cada rota melhor encontrada,
    para a tela já mostrar a primeira (uns 7 s) enquanto o resto é refinado.
    `voltas=0` pula o passo 3 (resposta mais rápida, ex.: no meio da rota).
    None se não houver nenhuma."""
    candidatas = _pedir_principal(origem, destino, rumo, destino_nome, "tranquila", alternativas=2)
    vistas = []
    if rapida is not None:
        esperar(ESPERA_ENTRE_S)
        if medir_movimento(rapida) is not None:
            vistas.append(rapida)
    limite_s = None if rapida is None else rapida.tempo_base_s * TRANQUILA_MAIS_LONGA + 180

    def serve(c):
        return c.movimentada is not None and (limite_s is None or c.tempo_base_s <= limite_s)
    melhor = None
    for c in candidatas:
        if rapida is not None and rapida.movimentada is not None and parecidas(c, rapida):
            continue                                    # é a própria rápida
        esperar(ESPERA_ENTRE_S)
        if medir_movimento(c) is None:
            continue
        vistas.append(c)
        if serve(c) and (melhor is None or c.estresse < melhor.estresse):
            melhor = c
    if melhor is not None and ao_melhorar is not None and voltas:
        ao_melhorar(melhor)
    for _ in range(voltas):
        evitar = sorted((p for r in vistas for p in getattr(r, "_evitar", ())), key=lambda t: -t[1])
        evitar = [ponto for ponto, _ in evitar
                  if distancia_m(ponto, origem) > 250 and distancia_m(ponto, destino) > 250][:EVITAR_MAX]
        if not evitar:
            break                                       # nenhuma avenida para contornar
        try:
            esperar(ESPERA_ENTRE_S)
            nova = _pedir_principal(origem, destino, rumo, destino_nome, "tranquila", evitar=evitar)
            esperar(ESPERA_ENTRE_S)
            if medir_movimento(nova) is None:
                break
        except Exception as e:                          # sem caminho contornando tudo, ou servidor ocupado
            print("[rota] contornar avenidas:", e)
            break
        vistas.append(nova)
        if not serve(nova) or (melhor is not None and nova.estresse >= melhor.estresse - 0.05):
            break                                       # não melhorou: para de tentar
        melhor = nova
    # sem medida nenhuma (servidor não respondeu): fica a primeira, como antes
    return melhor if melhor is not None else (candidatas[0] if candidatas else None)


def pedir_rota(origem, destino, rumo=None, destino_nome="", perfil="rapida"):
    """Chamada que espera a resposta (use rede.em_segundo_plano). Se o
    servidor principal não responder, a rota mais rápida vem do reserva."""
    try:
        return _pedir_principal(origem, destino, rumo, destino_nome, perfil)
    except SemRota:
        raise
    except Exception as erro:
        if perfil != "rapida":
            raise
        print("[rota] servidor principal falhou (%s): tentando o reserva" % erro)
        try:
            return _pedir_reserva(origem, destino, destino_nome)
        except SemRota:
            raise
        except Exception as erro2:
            print("[rota] reserva tambem falhou:", erro2)
            raise erro


def _pedir_principal(origem, destino, rumo, destino_nome, perfil, alternativas=0, evitar=()):
    """Uma Rota; com `alternativas` > 0, a lista [principal, alternativas...].
    `evitar`: pontos (lat, lon) por onde a rota não pode passar."""
    opcoes = {"bicycle_type": "Hybrid", "cycling_speed": 22}   # bike elétrica na cidade
    opcoes.update(dict((p[0], p[2]) for p in PERFIS)[perfil])
    partida = {"lat": origem[0], "lon": origem[1]}
    if rumo is not None:
        # já pedalando: evita uma rota que comece com meia-volta
        partida.update(heading=int(rumo) % 360, heading_tolerance=60)
    pedido = {
        "locations": [partida, {"lat": destino[0], "lon": destino[1]}],
        "costing": "bicycle",
        "costing_options": {"bicycle": opcoes},
        "language": "pt-BR",
        "directions_options": {"language": "pt-BR", "units": "kilometers"},
        "elevation_interval": ELEVACAO_PASSO_M,
    }
    if alternativas:
        pedido["alternates"] = alternativas
    if evitar:
        pedido["exclude_locations"] = [{"lat": p[0], "lon": p[1]} for p in evitar]
    url = VALHALLA + "?json=" + urllib.parse.quote(json.dumps(pedido))
    try:
        try:
            dados = rede.baixar_json(url, timeout=ESPERA_PRINCIPAL_S)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503):
                raise
            # servidor gratuito pedindo calma (ex.: logo depois das rotas
            # alternativas): espera um pouco e tenta de novo uma vez
            time.sleep(1.5)
            dados = rede.baixar_json(url, timeout=ESPERA_PRINCIPAL_S)
    except urllib.error.HTTPError as e:
        if e.code == 400:  # ex.: "No path could be found for input" (erro 442)
            try:
                codigo = json.loads(e.read().decode("utf-8")).get("error_code")
            except ValueError:
                codigo = None
            if codigo == 154:
                raise SemRota("Longe demais: rota de bike vai até 150 km.")
            raise SemRota("Não achei um caminho de bike até esse lugar.")
        raise
    todas = [Rota.do_valhalla(d, destino_nome) for d in [dados] + list(dados.get("alternates") or [])]
    for rota in todas:
        rota.perfil = perfil
    return todas if alternativas else todas[0]


def _dist_segmento(p, a, b):
    """Metros do ponto p ao segmento ab (plano local; serve para cidade)."""
    k = math.cos(math.radians(p[0])) * 111320.0
    ax, ay = (a[1] - p[1]) * k, (a[0] - p[0]) * 111320.0
    bx, by = (b[1] - p[1]) * k, (b[0] - p[0]) * 111320.0
    dx, dy = bx - ax, by - ay
    c2 = dx * dx + dy * dy
    t = 0.0 if c2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / c2))
    return math.hypot(ax + t * dx, ay + t * dy)


def parecidas(a, b):
    """Duas rotas praticamente iguais (mesma distância e mesmo caminho)."""
    if abs(a.total_m - b.total_m) > 0.03 * max(a.total_m, b.total_m) + 30:
        return False
    for k in range(1, 12):
        p = a.ponto_em(a.total_m * k / 12.0)
        if min(_dist_segmento(p, q, r) for q, r in zip(b.pontos, b.pontos[1:])) > 40:
            return False
    return True


def pedir_alternativas(origem, destino, rumo=None, destino_nome="", ja=(), ao_parcial=None, voltas=EVITAR_VOLTAS,
                       chave_tomtom=None):
    """As outras rotas (perfis de PERFIS que ainda não estão em `ja`), sem as
    repetidas. Uma de cada vez: o servidor é gratuito e compartilhado.
    `ao_parcial(lista)`: chamado (na thread da busca) quando a primeira rota
    tranquila aparece, antes de terminar de refinar."""
    rotas = list(ja)
    tem = {r.perfil for r in rotas}

    def parcial(calma):
        if ao_parcial is not None and not any(parecidas(r, calma) for r in rotas):
            ao_parcial(rotular(rotas + [calma]))
    if chave_tomtom and "transito" not in tem:
        # a rota que sabe do trânsito de agora (TomTom): um pedido só, chega logo
        try:
            import rota_tomtom
            viva = rota_tomtom.pedir(chave_tomtom, origem, destino, rumo, destino_nome)
            if viva is not None:
                igual = next((r for r in rotas if parecidas(r, viva)), None)
                if igual is None:
                    rotas.append(viva)
                    if ao_parcial is not None:
                        ao_parcial(rotular(rotas))
                else:   # é o mesmo caminho de uma que já existe: ela ganha o tempo com trânsito
                    igual.tempo_tomtom_s = viva.tempo_base_s
        except Exception as e:   # (sem o texto do erro quando for de rede: o endereço leva a chave)
            print("[rota] TomTom falhou:", type(e).__name__, getattr(e, "code", ""))
    for perfil, nome, _ in PERFIS:
        if perfil in tem:
            continue
        try:
            if perfil == "tranquila":
                nova = mais_tranquila(origem, destino, rumo, destino_nome, rotas[0] if rotas else None,
                                      voltas=voltas, ao_melhorar=parcial)
            else:
                time.sleep(ESPERA_ENTRE_S)
                nova = pedir_rota(origem, destino, rumo, destino_nome, perfil)
        except Exception as e:
            print("[rota] perfil", perfil, "falhou:", e)
            continue
        if nova is None:
            continue
        igual = next((r for r in rotas if parecidas(r, nova)), None)
        if igual is None:
            rotas.append(nova)
        elif perfil == "tranquila":
            igual.perfil_tranquilo = True
    return rotular(rotas)


def rotular(rotas):
    """As rotas com o nome certo, a mais rápida primeiro. A que veio da
    TomTom ("Pelo trânsito de agora") fica sempre, no fim: o tempo dela é
    medido de outro jeito (com trânsito), não se compara com o das outras."""
    vivas = [r for r in rotas if r.perfil == "transito"]
    return _rotular_bike([r for r in rotas if r.perfil != "transito"]) + vivas


def _rotular_bike(rotas):
    """Nome de cada rota pelos NÚMEROS dela (o servidor nem sempre acerta: a
    "menos subida" pedida às vezes sobe mais). Rota que não é a melhor em
    nada sai da lista. A primeira é sempre a mais rápida."""
    if len(rotas) <= 1:
        for r in rotas:
            r.nome_perfil = "Mais rápida"
        return rotas
    rapida = min(rotas, key=lambda r: r.tempo_s)
    curta = min(rotas, key=lambda r: r.total_m)
    plana = min(rotas, key=lambda r: r.subida_total_m)
    boas = []
    for r in rotas:
        nomes = []
        if r is rapida:
            nomes.append("rápida")
        if r is curta and r.total_m < rapida.total_m - 50:
            nomes.append("curta")
        if r is plana and r.subida_total_m < rapida.subida_total_m - 5:
            nomes.append("menos subida")
        if (r.perfil == "tranquila" or getattr(r, "perfil_tranquilo", False)) and r is not rapida:
            # com as duas medidas, só é "tranquila" se tiver mesmo menos avenida
            medidas = r.estresse is not None and rapida.estresse is not None
            if not medidas or (r.estresse <= rapida.estresse * 0.85
                               and r.movimentada <= rapida.movimentada - TRANQUILA_GANHO / 2):
                nomes.append("tranquila")
        if nomes:
            if nomes[0] == "menos subida":
                r.nome_perfil = "Menos subida" + "".join(" e " + n for n in nomes[1:])
            else:
                texto = " e ".join(nomes)
                r.nome_perfil = "Mais " + texto.replace(" e menos subida", ", menos subida")
            boas.append(r)
    boas.sort(key=lambda r: r is not rapida)
    if not any("tranquila" in r.nome_perfil for r in boas) and (
            getattr(rapida, "perfil_tranquilo", False)
            or (rapida.movimentada is not None and any(r.perfil == "tranquila" for r in rotas))):
        # procurou e não há caminho mais calmo: a pessoa fica sabendo
        rapida.nome_perfil = "Mais rápida (não achei mais calma)"
    return boas
