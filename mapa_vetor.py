"""Dados do mapa vetorial (OpenFreeMap: grátis, sem conta, dados do
OpenStreetMap no esquema OpenMapTiles).

Em segundo plano (threads), para cada tile visível: baixa o .pbf (cache em
disco de 30 dias), decodifica (mvt.py) e PREPARA a geometria já em
triângulos, no estilo do app e na espessura certa para o zoom de desenho:
  - áreas (parque, água, prédios...) -> triângulos pelo Tesselator do Kivy
  - ruas -> faixas com espessura por classe + juntas arredondadas
  - nomes de rua, bairros e lugares -> candidatos a rótulo (a tela escolhe
    quais cabem)
A thread do Kivy só transforma as listas prontas em Mesh (rápido). O app
nunca trava esperando o mapa.

Fluidez (medida em 01/10/2026): no Python só uma thread roda por vez (GIL).
Com 2 threads preparando, a tela esperava a vez e travava até 1 s no zoom;
e o tesselador (código C) segura a vez inteira enquanto roda: os prédios
vêm TODOS juntos numa feição só (até ~3000 pontos) e travavam a tela 50 ms
de uma vez no PC (bem mais no celular). Por isso: UMA thread, e cada
polígono vai sozinho para o tesselador (prédio simples nem passa por ele).

Coordenadas "locais": pixels do Web Mercator no zoom 14, menos uma origem
fixa, com Y para cima (como no Kivy).
"""
import collections
import marshal
import math
import unicodedata
from array import array
import os
import sqlite3
import threading
import time
import urllib.error
import zlib

from kivy.clock import Clock
from kivy.graphics.tesselator import TYPE_POLYGONS, WINDING_ODD, Tesselator

import goiania
import mvt
import rede

TILEJSON = "https://tiles.openfreemap.org/planet"
URL_PADRAO = "https://tiles.openfreemap.org/planet/20260927_080001_pt/{z}/{x}/{y}.pbf"
Z_DADOS_MAX = 14
# Goiânia INTEIRA vem dentro do app (pedido do dono, 07/10/2026: o mapa
# demorava a aparecer ao arrastar e dar zoom porque cada pedaço era baixado
# na hora). Feito por ferramentas/empacotar_mapa.py.
PACOTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados", "goiania_mapa.db")
VALIDADE_S = 30 * 86400
TRABALHADORES = 1          # mais threads = a tela espera mais pela vez (GIL)
# Memória (o dono relatou o app fechando no zoom, 01/10/2026): um tile
# preparado ocupava ~8,5 MB em listas de float do Python e cabiam 64 (fora os
# decodificados) -> centenas de MB no celular. Agora os vértices vão em
# array (4 bytes por número, ~8x menos) e cabem menos tiles.
MAX_PREPARADOS = 56
# Pedaços do mapa JÁ DESENHADOS ficam guardados no celular (pedido do dono,
# 07/10/2026: "o app já abre com o mapa carregado; dou zoom, movo e ele já está
# carregado"). Preparar um pedaço no zoom de navegação leva ~0,3 s no PC e
# mais de 2 s no celular; ler o pronto do disco leva milésimos. Mudou
# preparar() ou o estilo (larguras, zoom mínimo de cada rua)? Suba este número:
VERSAO_PREPARO = 1
# formato do marshal fixo (2 = o que todo Python lê): o pacote é montado no PC/GitHub
# com um Python e lido no celular com outro
FORMATO_MARSHAL = 2
# ... e os zooms mais usados da cidade INTEIRA já vêm prontos dentro do APK
# (dados/mapa_pronto.db, montado a cada build por ferramentas/empacotar_prontos.py):
# a cidade vista de longe (11 a 14), o mapa livre (16) e a navegação (17). Os outros
# zooms são desenhados na primeira vez e guardados no celular.
PRONTOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados", "mapa_pronto.db")
ZOOMS_PRONTOS = (11, 12, 13, 14, 16, 17)
DENSIDADE_PRONTOS = 2.75   # celular comum; só muda detalhes menores que 1 px
MAX_DECODIFICADOS = 12
LIMITE_DISCO_MB = 450
MAX_VERTICES_MESH = 60000  # índices do Mesh são de 16 bits
MAX_INDICES_MESH = 60000   # e o Kivy recusa (erro!) Mesh com mais de 65535 índices
# os nomes candidatos do tile ficam numa grade de GRADE x GRADE quadrados: a
# tela olha só os quadrados à vista (no zoom de navegação um tile é ~10x a
# tela; olhar os milhares de candidatos do tile a cada 0,45 s custava caro)
GRADE = 8
REDESCOBRIR_S = 120        # no máximo uma nova consulta da versão a cada isso
# enquanto a tela anima (seta andando, zoom, arrasto), a thread do mapa
# trabalha em fatias de FATIA_S e dorme PAUSA_S entre elas: a tela tem a vez
# sempre que precisa. Mapa parado: trabalha direto.
FATIA_S = 0.003
PAUSA_S = 0.003

# --- estilo (cores RGBA; larguras em dp no zoom 16) ---------------------------
# Tema escuro no estilo do Waze (pedido do dono, com um print do Waze,
# 06/10/2026): fundo azul-acinzentado (não mais quase preto), ruas LARGAS num
# tom um pouco mais claro que o fundo, hierarquia só pelo brilho e pela
# largura (sem avenidas cor de areia). O mapa fica calmo e a rota, o que
# tem cor, salta.
FUNDO = [0.118, 0.141, 0.188, 1]   # (lista: aplicar_tema troca o conteúdo no lugar)
# (a ordem é a do desenho: o prédio fica por cima do terreno)
AREAS = {
    "residencial": (0.128, 0.153, 0.203, 1),
    "comercial": (0.142, 0.152, 0.198, 1),
    "institucional": (0.150, 0.188, 0.275, 1),   # escola, faculdade, hospital: bloco azulado
    "verde": (0.160, 0.385, 0.310, 1),           # praça, parque, campo
    "agua": (0.150, 0.290, 0.560, 1),
    "predio": (0.152, 0.180, 0.238, 1),
}
# Tema claro (dia): mapa de fundo cinza-claro com ruas brancas e avenidas
# amarelas, como os mapas de papel; o escuro são os valores deste arquivo.
# (08/10/2026, com um print do dono no celular: o mapa claro estava "chapado",
# ruas brancas num fundo cinza sem definição e a avenida igual às ruas. Agora:
# fundo mais claro, CONTORNO nas ruas, e avenidas em amarelo que se vê.)
_CLARO = {
    "fundo": (0.935, 0.938, 0.925, 1),
    "contorno": (0.775, 0.795, 0.815, 1),
    "areas": {"residencial": (0.948, 0.950, 0.938, 1), "comercial": (0.968, 0.948, 0.905, 1),
              "institucional": (0.905, 0.920, 0.968, 1), "verde": (0.760, 0.895, 0.765, 1),
              "agua": (0.640, 0.810, 0.955, 1), "predio": (0.868, 0.868, 0.850, 1)},
    "ruas": {"servico": (0.975, 0.978, 0.982, 1), "caminho": (0.830, 0.850, 0.865, 1),
             "ciclovia": (0.150, 0.640, 0.420, 1), "rua": (1.0, 1.0, 1.0, 1),
             "terciaria": (1.0, 0.985, 0.900, 1), "secundaria": (1.0, 0.930, 0.640, 1),
             "primaria": (1.0, 0.860, 0.470, 1), "expressa": (0.985, 0.760, 0.380, 1)},
    # (mais apagadas que no escuro: em cima de rua branca, seta escura cheia pesava o mapa)
    "setas": {"setas": (0.420, 0.490, 0.560, 0.50), "setas_escuras": (0.470, 0.410, 0.270, 0.55)},
}
_ESCURO = None   # guardado na primeira troca
_USO_DO_SOLO = {
    "residential": "residencial", "suburb": "residencial", "neighbourhood": "residencial",
    "commercial": "comercial", "retail": "comercial",
    "school": "institucional", "university": "institucional", "college": "institucional",
    "hospital": "institucional", "kindergarten": "institucional",
    "cemetery": "verde", "pitch": "verde", "playground": "verde", "stadium": "verde",
}
# Mão única (o dono pediu a contramão bem clara, sem exagero): setinhas no
# sentido da rua, a partir do zoom 16, uma a cada SETA_PASSO_DP de rua.
ZOOM_SETAS = 16
SETA_PASSO_DP = 120.0
SETA_TAM_DP = 6.5          # metade do comprimento da seta
SETAS = {  # nome do grupo -> cor (discretas: informam o sentido sem sujar o mapa)
    "setas": (0.60, 0.68, 0.80, 0.55),
    "setas_escuras": (0.64, 0.72, 0.84, 0.55),
}
_SETA_ESCURA = ("primaria", "secundaria")
_COM_SETA = ("rua", "terciaria", "secundaria", "primaria")
# (largura dp no z16, cor, zoom mínimo)
# Hierarquia (o dono achou o mapa de longe uma "teia" branca): rua comum só
# a partir do zoom 14; avenidas e vias expressas num tom areia que se
# destaca de longe (como os mapas de navegação), o resto em cinza-azulado.
# Contorno das ruas: de perto, cada rua é desenhada duas vezes (uma mais larga,
# nesta cor, por baixo): a borda fina dá definição ao desenho, como nos mapas
# do Google e do Waze. (lista: aplicar_tema troca o conteúdo no lugar)
CONTORNO = [0.082, 0.100, 0.138, 1]
ZOOM_CONTORNO = 15         # de mais longe as ruas são finas demais para a borda aparecer
CONTORNO_PX = 1.1          # largura da borda de cada lado, em px de tela
RUAS = collections.OrderedDict([
    ("servico", (3.0, (0.196, 0.236, 0.302, 1), 15)),
    ("caminho", (2.2, (0.184, 0.222, 0.284, 1), 15)),
    ("ciclovia", (3.0, (0.200, 0.620, 0.450, 1), 14)),
    ("rua", (6.0, (0.248, 0.298, 0.380, 1), 14)),
    ("terciaria", (7.2, (0.278, 0.334, 0.422, 1), 13)),
    ("secundaria", (8.4, (0.308, 0.370, 0.466, 1), 10)),
    ("primaria", (9.4, (0.342, 0.410, 0.516, 1), 8)),
    ("expressa", (10.4, (0.382, 0.458, 0.574, 1), 6)),
])
_CLASSE_RUA = {
    "motorway": "expressa", "trunk": "expressa", "primary": "primaria",
    "secondary": "secundaria", "tertiary": "terciaria", "minor": "rua",
    "service": "servico", "track": "servico", "path": "caminho",
    "busway": "rua", "raceway": "rua", "pedestrian": "caminho",
}
_IMPORTANCIA = {"expressa": 7, "primaria": 6, "secundaria": 5, "terciaria": 4,
                "rua": 3, "ciclovia": 2, "servico": 1, "caminho": 1}


def fator_largura(rz):
    """Ruas engrossam com o zoom (como nos mapas de verdade)."""
    return {11: 0.30, 12: 0.38, 13: 0.48, 14: 0.62, 15: 0.80, 16: 1.0,
            17: 1.28, 18: 1.6, 19: 2.0}.get(rz, 0.30 if rz < 11 else 2.0)


# lugares que só poluem a tela de quem pedala
_POI_IGNORAR = {"railway", "toilets", "atm", "bench", "waste_basket", "parking",
                "bicycle_parking", "post", "telephone", "vending", "recycling",
                "gate", "lift_gate", "swimming_pool", "shelter"}
# Cada lugar tem um GRUPO (a cor da bolinha e do nome no mapa) e uma
# LEGENDA (o que ele é: aparece ao lado do nome de perto, "Pão Bom · padaria",
# quando o próprio nome já não diz). classe do mapa -> (grupo, legenda)
_POI_CATEGORIA = {
    "park": ("praca", "praça"), "garden": ("praca", "jardim"), "playground": ("praca", "parquinho"),
    "restaurant": ("comida", "restaurante"), "fast_food": ("comida", "lanchonete"),
    "bakery": ("comida", "padaria"), "cafe": ("comida", "café"), "bar": ("comida", "bar"),
    "beer": ("comida", "bar"), "ice_cream": ("comida", "sorveteria"),
    "grocery": ("compras", "mercado"), "shop": ("compras", "loja"),
    "clothing_store": ("compras", "roupas"), "alcohol_shop": ("compras", "bebidas"),
    "butcher": ("compras", "açougue"), "bicycle": ("compras", "bicicletaria"),
    "car": ("compras", "veículos"), "hairdresser": ("compras", "salão"),
    "hospital": ("saude", "saúde"), "pharmacy": ("saude", "farmácia"), "dentist": ("saude", "dentista"),
    "doctors": ("saude", "médico"), "veterinary": ("saude", "veterinário"),
    "school": ("ensino", "escola"), "college": ("ensino", "faculdade"), "library": ("ensino", "biblioteca"),
    "bank": ("servico", "banco"), "office": ("servico", "escritório"), "police": ("servico", "polícia"),
    "fire_station": ("servico", "bombeiros"), "town_hall": ("servico", "órgão público"),
    "fuel": ("servico", "posto"), "lodging": ("servico", "hotel"), "bus": ("servico", "ônibus"),
    "place_of_worship": ("lazer", "templo"), "pitch": ("lazer", "quadra"),
    "sports_centre": ("lazer", "esportes"), "stadium": ("lazer", "estádio"),
    "museum": ("lazer", "museu"), "theatre": ("lazer", "teatro"), "cinema": ("lazer", "cinema"),
    "attraction": ("lazer", "atração"), "monument": ("lazer", "monumento"),
    "art_gallery": ("lazer", "arte"), "water_park": ("lazer", "parque aquático"),
    "cemetery": ("lazer", "cemitério"),
}
_POI_SUBCLASSE = {  # legenda mais exata quando o mapa diz o subtipo
    "supermarket": "supermercado", "marketplace": "feira", "mall": "shopping",
    "department_store": "loja de departamentos", "convenience": "conveniência",
    "clinic": "clínica", "hospital": "hospital", "university": "universidade",
    "kindergarten": "creche", "government": "órgão público", "company": "empresa",
    "car_repair": "oficina", "car_parts": "autopeças", "motorcycle": "motos", "pet": "pet shop",
    "beauty": "salão", "electronics": "eletrônicos", "hardware": "ferragens",
    "doityourself": "ferragens", "furniture": "móveis", "shoes": "calçados", "motel": "motel",
    "christian": "igreja", "courthouse": "fórum", "townhall": "prefeitura", "soccer": "campo",
}
_JA_DIZ = {  # o nome já explica: não repete a legenda
    "praça": ("praca", "parque", "bosque", "jardim"), "igreja": ("igreja", "paroquia", "capela", "catedral",
                                                               "congregacao", "assembleia", "templo"),
    "escola": ("escola", "colegio", "cmei", "centro de ensino"), "posto": ("posto",),
    "restaurante": ("restaurante", "churrascaria", "pizzaria"), "padaria": ("padaria", "panificadora"),
    "farmácia": ("farmacia", "drogaria", "drogasil"), "supermercado": ("supermercado", "atacad"),
    "universidade": ("universidade", "faculdade", "campus", "ufg", "puc", "ueg"),
    "faculdade": ("universidade", "faculdade", "senai", "senac", "sest"),
    "clínica": ("clinica", "cais", "ciams", "upa", "csf", "consultorio"), "hospital": ("hospital",),
    "saúde": ("hospital", "clinica", "saude"), "hotel": ("hotel", "pousada"), "banco": ("banco", "caixa", "sicoob"),
    "bar": ("bar ", "boteco", "pub"), "lanchonete": ("lanch", "burger", "pastel", "acai"),
    "campo": ("campo", "quadra", "estadio"), "quadra": ("campo", "quadra", "ginasio"),
    "ônibus": ("terminal", "rodoviaria", "onibus"), "shopping": ("shopping",),
}


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def categoria_poi(classe, subclasse, nome=""):
    """(grupo, legenda) do lugar; legenda "" se o nome já diz o que ele é."""
    grupo, legenda = _POI_CATEGORIA.get(classe, ("outros", ""))
    return grupo, legenda_se_precisa(nome, _POI_SUBCLASSE.get(subclasse, legenda))


def legenda_se_precisa(nome, legenda):
    """A legenda, ou "" se o nome já diz o que o lugar é."""
    limpo = _sem_acento(nome) + " "
    if legenda and any(p in limpo for p in _JA_DIZ.get(legenda, (_sem_acento(legenda),))):
        return ""
    return legenda


def chave_nome(texto):
    """Para não mostrar o mesmo lugar duas vezes (mapa + base da busca)."""
    return _sem_acento(texto.split(" · ")[0]).strip()


def aplicar_tema(claro):
    """Troca as cores do mapa (no lugar). Vale para os tiles preparados
    DEPOIS: quem chama remonta o mapa."""
    global _ESCURO
    if _ESCURO is None:
        _ESCURO = {"fundo": tuple(FUNDO), "contorno": tuple(CONTORNO), "areas": dict(AREAS),
                   "ruas": {n: v[1] for n, v in RUAS.items()}, "setas": dict(SETAS)}
    estilo = _CLARO if claro else _ESCURO
    FUNDO[:] = estilo["fundo"]
    CONTORNO[:] = estilo["contorno"]
    AREAS.update(estilo["areas"])
    SETAS.update(estilo["setas"])
    for nome, (largura, _, zoom_min) in list(RUAS.items()):
        RUAS[nome] = (largura, estilo["ruas"][nome], zoom_min)


def cor_rua(nome, rz):
    """De longe, ruas pequenas mais apagadas, puxadas para a cor do fundo
    (senão viram uma teia que compete com as avenidas e com a rota)."""
    r, g, b, a = RUAS[nome][1]
    f = 1.0
    if nome in ("rua", "servico", "caminho") and rz <= 14:
        f = 0.62 if rz <= 13 else 0.75
    elif nome == "terciaria" and rz <= 13:
        f = 0.7
    if f == 1.0:
        return RUAS[nome][1]
    return (FUNDO[0] + (r - FUNDO[0]) * f, FUNDO[1] + (g - FUNDO[1]) * f, FUNDO[2] + (b - FUNDO[2]) * f, a)


def z_dados(rz):
    return max(0, min(Z_DADOS_MAX, rz))


def tiles_do_retangulo(x0, y0, x1, y1, dz):
    """Tiles do zoom de dados dz que cobrem o retângulo em px do mundo z14."""
    lado = 256.0 * 2 ** (14 - dz)
    n = 2 ** dz
    tx0, tx1 = int(math.floor(x0 / lado)), int(math.floor(x1 / lado))
    ty0, ty1 = max(0, int(math.floor(y0 / lado))), min(n - 1, int(math.floor(y1 / lado)))
    return [(tx, ty) for tx in range(tx0, tx1 + 1) for ty in range(ty0, ty1 + 1)]


_tela = {"animando_ate": 0.0, "ultimo_respiro": 0.0}


def tela_animando():
    """A tela chama a cada quadro de animação."""
    _tela["animando_ate"] = time.monotonic() + 0.3


def _respirar():
    """Chamado pela thread do mapa a cada pedacinho de trabalho."""
    agora = time.perf_counter()
    if agora - _tela["ultimo_respiro"] >= FATIA_S:
        time.sleep(PAUSA_S if time.monotonic() < _tela["animando_ate"] else 0)
        _tela["ultimo_respiro"] = time.perf_counter()


# --- geometria ------------------------------------------------------------------
def _area2(pts):
    """Duas vezes a área com sinal (o sinal diz o sentido do anel)."""
    a = 0.0
    x0, y0 = pts[-1]
    for x1, y1 in pts:
        a += x0 * y1 - x1 * y0
        x0, y0 = x1, y1
    return a


def _poligonos(aneis):
    """Anéis do MVT -> polígonos [externo, furos...]. O 1º anel é sempre
    externo; os de mesmo sentido abrem um polígono novo."""
    polis, sentido = [], None
    for anel, a in aneis:
        if sentido is None:
            sentido = a > 0
        if (a > 0) == sentido or not polis:
            polis.append([anel])
        else:
            polis[-1].append(anel)
    return polis


def _convexo(pts):
    """Anel sem "dentes" (a maioria dos prédios): vira leque de triângulos
    direto, sem passar pelo tesselador."""
    n = len(pts)
    if n < 3:
        return False
    sinal = 0
    for k in range(n):
        ax, ay = pts[k - 2]
        bx, by = pts[k - 1]
        cx, cy = pts[k]
        z = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if z:
            if sinal == 0:
                sinal = 1 if z > 0 else -1
            elif (z > 0) != (sinal > 0):
                return False
    return True


def _simplificar(pts, tol2):
    """Douglas-Peucker (tolerância ao quadrado), iterativo."""
    if len(pts) < 3:
        return pts
    manter = [False] * len(pts)
    manter[0] = manter[-1] = True
    pilha = [(0, len(pts) - 1)]
    while pilha:
        a, b = pilha.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        comp2 = dx * dx + dy * dy or 1e-12
        pior, idx = 0.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            t = ((px - ax) * dx + (py - ay) * dy) / comp2
            t = 0.0 if t < 0 else (1.0 if t > 1 else t)
            qx, qy = ax + t * dx - px, ay + t * dy - py
            d2 = qx * qx + qy * qy
            if d2 > pior:
                pior, idx = d2, i
        if pior > tol2 and idx > 0:
            manter[idx] = True
            pilha += [(a, idx), (idx, b)]
    return [p for p, m in zip(pts, manter) if m]


class _Malha:
    """Acumula triângulos e corta em pedaços de até MAX_VERTICES_MESH
    vértices e MAX_INDICES_MESH índices."""

    def __init__(self):
        self.pedacos = [([], [])]

    def _atual(self, novos, novos_indices):
        v, i = self.pedacos[-1]
        if len(v) // 4 + novos > MAX_VERTICES_MESH or len(i) + novos_indices > MAX_INDICES_MESH:
            self.pedacos.append(([], []))
        return self.pedacos[-1]

    def leque(self, cx, cy, r, lados=7):
        v, ind = self._atual(lados + 1, 3 * lados)
        base = len(v) // 4
        v += [cx, cy, 0, 0]
        for k in range(lados):
            a = 2 * math.pi * k / lados
            v += [cx + r * math.cos(a), cy + r * math.sin(a), 0, 0]
        for k in range(lados):
            ind += [base, base + 1 + k, base + 1 + (k + 1) % lados]

    def faixa(self, pts, meia, lados_junta=0):
        """Rua de largura 2*meia; lados_junta > 0 arredonda curvas e pontas."""
        if len(pts) < 2:
            return
        v, ind = self._atual(len(pts) * 4, len(pts) * 6)
        base = len(v) // 4
        n_quad = 0
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            dx, dy = bx - ax, by - ay
            comp = math.hypot(dx, dy)
            if comp < 1e-9:
                continue
            nx, ny = -dy / comp * meia, dx / comp * meia
            b0 = base + n_quad * 4
            v += [ax + nx, ay + ny, 0, 0, ax - nx, ay - ny, 0, 0,
                  bx - nx, by - ny, 0, 0, bx + nx, by + ny, 0, 0]
            ind += [b0, b0 + 1, b0 + 2, b0, b0 + 2, b0 + 3]
            n_quad += 1
        if lados_junta:
            for k in range(len(pts)):
                self.leque(pts[k][0], pts[k][1], meia, lados_junta)

    def triangulos(self, vertices, indices_leque):
        v, ind = self._atual(len(vertices) // 4, 3 * max(0, len(indices_leque) - 2))
        base = len(v) // 4
        v += vertices
        for k in range(1, len(indices_leque) - 1):
            ind += [base + indices_leque[0], base + indices_leque[k], base + indices_leque[k + 1]]

    def seta(self, x, y, ux, uy, t):
        """Setinha de comprimento 2*t no ponto (x, y), apontando para (ux, uy)."""
        nx, ny = -uy, ux
        self.triangulos([x + ux * t, y + uy * t, 0, 0,
                         x + nx * t * 0.6, y + ny * t * 0.6, 0, 0,
                         x - nx * t * 0.6, y - ny * t * 0.6, 0, 0], [0, 1, 2])
        h = t * 0.16  # haste
        self.triangulos([x + nx * h, y + ny * h, 0, 0, x - nx * h, y - ny * h, 0, 0,
                         x - ux * t - nx * h, y - uy * t - ny * h, 0, 0,
                         x - ux * t + nx * h, y - uy * t + ny * h, 0, 0], [0, 1, 2, 3])

    def listas(self):
        """[(vértices, índices)] em array compacto ('f' e 'H'), que o Mesh do
        Kivy usa direto, sem copiar para lista."""
        return [(array("f", v), array("H", i)) for v, i in self.pedacos if i]


def _por_setas(malha, pts, passo, t):
    """Setas de mão única ao longo da rua (pts já no sentido permitido):
    espalhadas por igual, só em trecho reto onde a seta cabe inteira."""
    comps = [math.hypot(bx - ax, by - ay) for (ax, ay), (bx, by) in zip(pts, pts[1:])]
    total = sum(comps)
    if total < passo * 0.4:
        return
    n = max(1, int(total // passo))
    alvos = [(k + 0.5) * total / n for k in range(n)]
    andado, i = 0.0, 0
    for alvo in alvos:
        while i < len(comps) - 1 and andado + comps[i] < alvo:
            andado += comps[i]
            i += 1
        comp = comps[i]
        if comp < 2.4 * t:
            continue
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        f = min(max((alvo - andado) / comp, 1.2 * t / comp), 1.0 - 1.2 * t / comp)
        malha.seta(ax + (bx - ax) * f, ay + (by - ay) * f, (bx - ax) / comp, (by - ay) / comp, t)


QUASE_RETO = math.radians(12)   # trecho de rua que desvia menos que isso ainda é "reto"


def _trechos_retos(pts):
    """Trechos quase retos da rua: [(comprimento, i0, i1)]. A rua vem
    picotada (cada curvinha, cada cruzamento quebra a linha); exigir UM
    segmento reto onde o nome inteiro coubesse deixava o mapa sem nomes de
    rua no zoom médio (só 14 candidatos de rua contra 484 de lugar)."""
    trechos, i0, n = [], 0, len(pts)
    while i0 < n - 1:
        ax, ay = pts[i0]
        dir0 = math.atan2(pts[i0 + 1][1] - ay, pts[i0 + 1][0] - ax)
        i1 = i0 + 1
        while i1 < n - 1:
            bx, by = pts[i1]
            cx, cy = pts[i1 + 1]
            seg = math.atan2(cy - by, cx - bx)
            corda = math.atan2(cy - ay, cx - ax)
            if (abs((seg - dir0 + math.pi) % (2 * math.pi) - math.pi) > QUASE_RETO
                    or abs((corda - dir0 + math.pi) % (2 * math.pi) - math.pi) > QUASE_RETO / 2):
                break
            i1 += 1
        bx, by = pts[i1]
        trechos.append((math.hypot(bx - ax, by - ay), i0, i1))
        i0 = i1
    return trechos


def preparar(camadas, dz, tx, ty, rz, origem, escala, densidade):
    """Geometria pronta (listas) do tile para desenhar no zoom rz."""
    lado = 256.0 * 2 ** (14 - dz)
    ox, oy = origem
    px_por_local = escala * 2.0 ** (rz - 14)          # px da tela por unidade local

    def conversor(extent):
        k = lado / extent
        bx, by = tx * lado - ox, oy - ty * lado

        def conv(parte):
            """Parte do mvt (array plano x, y, x, y...) -> [(x, y), ...] locais."""
            return [(bx + parte[i] * k, by - parte[i + 1] * k) for i in range(0, len(parte) - 1, 2)]
        return conv

    tol2 = (0.6 / px_por_local) ** 2                   # simplifica abaixo de ~0,6 px
    areas = {nome: _Malha() for nome in AREAS}
    tess_ok = True

    area_min2 = 2.0 * (1.0 / px_por_local) ** 2        # anel com menos de ~1 px²: invisível

    def area(nome_cor, partes, conv):
        nonlocal tess_ok
        aneis = []
        for parte in partes:
            pts = _simplificar(conv(parte), tol2)
            if len(pts) > 3 and pts[0] == pts[-1]:
                pts = pts[:-1]  # o MVT repete o 1º ponto para fechar
            if len(pts) >= 3:
                a = _area2(pts)
                if abs(a) >= area_min2:
                    aneis.append((pts, a))
        malha = areas[nome_cor]
        for poli in _poligonos(aneis):
            _respirar()
            if len(poli) == 1 and _convexo(poli[0]):
                pts = poli[0]
                malha.triangulos([v for x, y in pts for v in (x, y, 0, 0)], list(range(len(pts))))
                continue
            tess = Tesselator()
            for anel in poli:
                tess.add_contour([c for q in anel for c in q])
            try:
                if not tess.tesselate(WINDING_ODD, TYPE_POLYGONS):
                    continue
            except Exception:
                tess_ok = False
                continue
            for vertices, indices in tess.meshes:
                malha.triangulos(list(vertices), list(indices))

    for nome_camada, alvo in (("landuse", None), ("park", "verde"), ("landcover", "verde"),
                              ("water", "agua"), ("building", "predio")):
        if nome_camada not in camadas or (nome_camada == "building" and rz < 16):
            continue
        extent, feicoes = camadas[nome_camada]
        conv = conversor(extent)
        for tipo, props, partes in feicoes:
            _respirar()
            if tipo != 3:
                continue
            cor = alvo
            if nome_camada == "landuse":
                cor = _USO_DO_SOLO.get(props.get("class"))
            elif nome_camada == "landcover" and props.get("class") not in ("grass", "wood", "farmland", "scrub"):
                continue
            if cor:
                area(cor, partes, conv)

    ruas = {nome: _Malha() for nome in RUAS}
    contorno = _Malha()
    borda_local = CONTORNO_PX * densidade / px_por_local
    setas = {nome: _Malha() for nome in SETAS}
    seta_t = SETA_TAM_DP * (1.0 if rz <= 16 else 1.25) * densidade / px_por_local
    seta_passo = SETA_PASSO_DP * densidade / px_por_local
    rotulos = []
    if "transportation" in camadas:
        extent, feicoes = camadas["transportation"]
        conv = conversor(extent)
        for tipo, props, partes in feicoes:
            _respirar()
            if tipo != 2:
                continue
            estilo = _CLASSE_RUA.get(props.get("class"))
            if props.get("subclass") == "cycleway" or props.get("bicycle") == "designated":
                estilo = "ciclovia"
            if estilo is None or rz < RUAS[estilo][2]:
                continue
            largura_px = RUAS[estilo][0] * densidade * fator_largura(rz)
            if estilo in ("rua", "servico", "caminho") and rz <= 14:
                largura_px *= 0.7
            meia = largura_px / 2.0 / px_por_local
            # juntas redondas só onde a rua é grossa o bastante para o canto aparecer
            lados = 0 if largura_px < 3 else (6 if largura_px < 10 else 8)
            mao = props.get("oneway") if rz >= ZOOM_SETAS and estilo in _COM_SETA else None
            com_borda = rz >= ZOOM_CONTORNO and largura_px >= 4 and estilo not in ("caminho", "ciclovia")
            for parte in partes:
                pts = _simplificar(conv(parte), tol2)
                ruas[estilo].faixa(pts, meia, lados)
                if com_borda:
                    contorno.faixa(pts, meia + borda_local, lados)
                if mao in (1, -1) and len(pts) >= 2:
                    _por_setas(setas["setas_escuras" if estilo in _SETA_ESCURA else "setas"],
                               pts if mao == 1 else pts[::-1], seta_passo, seta_t)
    if "transportation_name" in camadas and rz >= 14:
        extent, feicoes = camadas["transportation_name"]
        conv = conversor(extent)
        # trecho curto demais para o nome caber nem no zoom mais aberto deste nível
        letra_local = 13.5 * densidade * 0.4 / (px_por_local * 0.6)
        for tipo, props, partes in feicoes:
            nome = props.get("name")
            if tipo != 2 or not nome:
                continue
            estilo = _CLASSE_RUA.get(props.get("class"), "rua")
            if rz < RUAS.get(estilo, (0, 0, 13))[2] + 1:
                continue
            for parte in partes:
                pts = conv(parte)
                if len(pts) < 2:
                    continue
                # os 2 trechos quase retos mais longos da parte: onde o nome cabe
                # (o mesmo nome não se repete perto na tela: ver widgets/mapa.py)
                for comp, i0, i1 in sorted(_trechos_retos(pts), reverse=True)[:2]:
                    if comp < len(nome) * letra_local:
                        break
                    (ax, ay), (bx, by) = pts[i0], pts[i1]
                    rotulos.append({"texto": nome, "x": (ax + bx) / 2, "y": (ay + by) / 2,
                                    "ang": math.atan2(by - ay, bx - ax), "comp": comp,
                                    "peso": _IMPORTANCIA.get(estilo, 1), "tipo": "rua"})
    if "place" in camadas and rz <= 16:
        extent, feicoes = camadas["place"]
        conv = conversor(extent)
        for tipo, props, partes in feicoes:
            nome, classe = props.get("name"), props.get("class")
            if tipo != 1 or not nome or classe not in ("city", "town", "suburb", "neighbourhood", "quarter", "village"):
                continue
            if classe in ("neighbourhood", "quarter") and rz < 14:
                continue
            x, y = conv(partes[0])[0]
            rotulos.append({"texto": nome, "x": x, "y": y, "ang": 0.0, "comp": 0,
                            "peso": 9 if classe in ("city", "town") else 8, "tipo": "lugar"})
    if "poi" in camadas and rz >= 15:
        extent, feicoes = camadas["poi"]
        conv = conversor(extent)
        for tipo, props, partes in feicoes:
            nome, classe, sub = props.get("name"), props.get("class"), props.get("subclass")
            if (tipo != 1 or not nome or classe in _POI_IGNORAR or nome.strip().isdigit()
                    or (classe == "bus" and sub != "bus_station")):
                continue
            grupo, legenda = categoria_poi(classe, sub, nome)
            rank = props.get("rank", 99)
            # de longe só os principais (praça vale mais: é referência); de perto, quase tudo
            if rank > (25 if rz >= 17 else (14 if grupo == "praca" else 7)):
                continue
            x, y = conv(partes[0])[0]
            texto = "%s · %s" % (nome, legenda) if legenda and rz >= 17 else nome
            rotulos.append({"texto": texto, "x": x, "y": y, "ang": 0.0, "comp": 0,
                            "peso": 0.5 - rank / 100.0 + (0.3 if grupo == "praca" else 0.0),
                            "tipo": "poi", "grupo": grupo})
    celula = lado / GRADE
    grade = {}
    for r in rotulos:
        grade.setdefault((int(r["x"] // celula), int(r["y"] // celula)), []).append(r)
    return {
        "areas": [(nome, m.listas()) for nome, m in areas.items()],
        "ruas": [("contorno", tuple(CONTORNO), contorno.listas())]
                + [(nome, cor_rua(nome, rz), m.listas()) for nome, m in ruas.items()]
                + [(nome, SETAS[nome], m.listas()) for nome, m in setas.items()],
        "rotulos": rotulos,
        "grade": grade,          # (gx, gy) -> nomes naquele quadrado (coord. locais / celula)
        "celula": celula,
        "ok": tess_ok,
    }


# --- pedaços prontos guardados no disco ------------------------------------------
def empacotar(preparado):
    """O pedaço preparado em bytes (as cores ficam de fora: dependem do tema)."""
    def cru(listas):
        return [(v.tobytes(), i.tobytes()) for v, i in listas]
    return zlib.compress(marshal.dumps({
        "areas": [(nome, cru(listas)) for nome, listas in preparado["areas"]],
        "ruas": [(nome, cru(listas)) for nome, _, listas in preparado["ruas"]],
        "rotulos": preparado["rotulos"], "celula": preparado["celula"]}, FORMATO_MARSHAL), 1)


def desempacotar(dados, rz):
    """O contrário de empacotar(), com as cores do tema de agora."""
    d = marshal.loads(zlib.decompress(dados))

    def listas(crus):
        saida = []
        for vb, ib in crus:
            v, i = array("f"), array("H")
            v.frombytes(vb)
            i.frombytes(ib)
            saida.append((v, i))
        return saida

    def cor(nome):
        if nome == "contorno":
            return tuple(CONTORNO)
        return cor_rua(nome, rz) if nome in RUAS else SETAS[nome]
    celula, grade = d["celula"], {}
    for r in d["rotulos"]:
        grade.setdefault((int(r["x"] // celula), int(r["y"] // celula)), []).append(r)
    return {"areas": [(nome, listas(crus)) for nome, crus in d["areas"]],
            "ruas": [(nome, cor(nome), listas(crus)) for nome, crus in d["ruas"]],
            "rotulos": d["rotulos"], "grade": grade, "celula": celula, "ok": True}


def origem_padrao():
    """O ponto (px do mundo no zoom 14) em torno do qual o mapa é desenhado:
    o centro de Goiânia. Fixo: os pedaços prontos dependem dele."""
    lat, lon = goiania.CENTRO
    n = 256.0 * 2.0 ** 14
    return ((lon + 180.0) / 360.0 * n,
            (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)


_prontos_apk = {"con": None, "falta": False, "trava": threading.Lock()}


def pronto_do_app(chave):
    """Os bytes (empacotar) do pedaço (dz, tx, ty, rz) que já veio desenhado
    dentro do APK, ou None."""
    if _prontos_apk["falta"]:
        return None
    dz, tx, ty, rz = chave
    try:
        with _prontos_apk["trava"]:
            con = _prontos_apk["con"]
            if con is None:
                if not os.path.exists(PRONTOS):
                    _prontos_apk["falta"] = True
                    return None
                con = sqlite3.connect(PRONTOS, check_same_thread=False)
                sobre = dict(con.execute("SELECT chave, valor FROM sobre").fetchall())
                # feito por outra versão do desenho, ou de outro mapa: não serve
                if (sobre.get("versao") != str(VERSAO_PREPARO) or sobre.get("mapa") != data_do_pacote()
                        or sobre.get("marshal") != str(FORMATO_MARSHAL)):
                    con.close()
                    _prontos_apk["falta"] = True
                    print("[mapa] os pedaços prontos do app são de outra versão: ignorados")
                    return None
                _prontos_apk["con"] = con
            linha = con.execute("SELECT dados FROM prontos WHERE rz = ? AND dz = ? AND tx = ? AND ty = ?",
                                (rz, dz, tx, ty)).fetchone()
        return linha[0] if linha else None
    except Exception as e:
        print("[mapa] prontos do app:", type(e).__name__, e)
        return None


# --- o mapa que vem dentro do app ---------------------------------------------
_pacote = {"con": None, "falta": False, "trava": threading.Lock()}


def do_pacote(z, x, y):
    """O tile (z, x, y) que veio DENTRO do app, ou None (fora de Goiânia, ou
    o app foi montado sem o pacote). Não usa a internet."""
    if _pacote["falta"]:
        return None
    try:
        with _pacote["trava"]:
            con = _pacote["con"]
            if con is None:
                if not os.path.exists(PACOTE):
                    _pacote["falta"] = True
                    return None
                con = _pacote["con"] = sqlite3.connect(PACOTE, check_same_thread=False)
            linha = con.execute("SELECT dados FROM tiles WHERE z = ? AND x = ? AND y = ?", (z, x, y)).fetchone()
        return zlib.decompress(linha[0]) if linha else None
    except Exception as e:
        print("[mapa] pacote:", e)
        return None


def data_do_pacote():
    """Quando o mapa embutido foi montado ("" sem pacote): pedaço pronto
    guardado de um mapa mais velho não serve."""
    do_pacote(0, 0, 0)
    try:
        with _pacote["trava"]:
            linha = _pacote["con"].execute("SELECT valor FROM sobre WHERE chave = 'feito_em'").fetchone()
        return linha[0] if linha else ""
    except Exception:
        return ""


def partes_no_pacote():
    """Quantos pedaços do mapa vieram dentro do app (0 = nenhum)."""
    if do_pacote(0, 0, 0) is None and _pacote["con"] is None:
        return 0
    try:
        with _pacote["trava"]:
            return _pacote["con"].execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
    except Exception:
        return 0


# --- download, cache e fila de preparo ------------------------------------------
class FonteVetorial:
    def __init__(self, pasta, origem, escala, densidade, ao_ficar_pronto):
        self.pasta = os.path.join(pasta, "vetor")
        os.makedirs(self.pasta, exist_ok=True)
        self.origem, self.escala, self.densidade = origem, escala, densidade
        self.ao_ficar_pronto = ao_ficar_pronto   # chamada na thread do Kivy com a chave
        self._url = URL_PADRAO
        self._t_descoberta = 0.0
        self._prontos = collections.OrderedDict()       # (dz, tx, ty, rz) -> preparado
        self._decodificados = collections.OrderedDict()  # (dz, tx, ty) -> camadas
        self._pedidos = collections.deque()
        self._adiantados = collections.deque()   # pedidos "para depois": vizinhos e zooms ao lado
        self._pendentes = set()
        # (a pasta leva tudo de que o desenho depende: muda um, os guardados antigos não servem)
        self._pasta_prontos = os.path.join(self.pasta, "prontos", "v%d-%s-%.2f-%s" % (
            VERSAO_PREPARO, data_do_pacote() or "rede", densidade, FORMATO_MARSHAL))
        self.lidos_do_disco = 0                  # (para o diagnóstico e os testes)
        self.lidos_do_app = 0
        self.preparados_agora = 0
        self._falhas = {}
        self._trava = threading.Lock()
        self._aviso = threading.Condition(self._trava)
        self._fechada = False
        threading.Thread(target=self._descobrir_versao, daemon=True).start()
        for _ in range(TRABALHADORES):
            threading.Thread(target=self._trabalhar, daemon=True).start()
        threading.Thread(target=self._limpar_disco, daemon=True).start()

    # --- mapa offline de Goiânia (botão nos Ajustes) --------------------------------
    @staticmethod
    def tiles_goiania(zooms=(11, 12, 13, 14)):
        """[(z, x, y)] que cobrem Goiânia (goiania.LIMITES)."""
        lat0, lon0, lat1, lon1 = goiania.LIMITES

        def tile(lat, lon, z):
            n = 2 ** z
            x = int((lon + 180.0) / 360.0 * n)
            y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
            return x, y
        lista = []
        for z in zooms:
            xa, ya = tile(lat1, lon0, z)
            xb, yb = tile(lat0, lon1, z)
            lista += [(z, x, y) for x in range(xa, xb + 1) for y in range(ya, yb + 1)]
        return lista

    def baixar_goiania(self, ao_progresso, ao_terminar):
        """Baixa (ou confere no disco) todos os tiles de Goiânia, numa thread.
        ao_progresso(feitos, total, mb) e ao_terminar(ok, falhas) na thread do Kivy."""
        def trabalhar():
            lista = self.tiles_goiania()
            total, ok, falhas, tamanho = len(lista), 0, 0, 0
            for n, (z, x, y) in enumerate(lista, 1):
                dados = self._ler_ou_baixar(z, x, y)
                if dados is None:
                    falhas += 1
                else:
                    ok += 1
                    tamanho += len(dados)
                if n % 5 == 0 or n == total:
                    Clock.schedule_once(lambda dt, f=n, mb=tamanho / 1e6: ao_progresso(f, total, mb))
            Clock.schedule_once(lambda dt: ao_terminar(ok, falhas))
        threading.Thread(target=trabalhar, daemon=True).start()

    def pronto(self, chave):
        p = self._prontos.get(chave)
        if p is not None:
            self._prontos.move_to_end(chave)
        return p

    def pedir(self, chave, adiantado=False):
        """Pede o preparo do tile (dz, tx, ty, rz) se ainda não tem.
        adiantado=True: ainda não está na tela (vizinho, zoom ao lado); só
        é feito quando não há nada da tela esperando."""
        if chave in self._prontos:
            return
        with self._trava:
            if adiantado:
                if chave in self._pendentes or chave in self._adiantados \
                        or time.time() - self._falhas.get(chave, 0) < 15:
                    return
                self._adiantados.append(chave)
                while len(self._adiantados) > 40:
                    self._adiantados.popleft()
                self._aviso.notify()
                return
            if chave in self._pendentes or time.time() - self._falhas.get(chave, 0) < 15:
                return
            self._pendentes.add(chave)
            self._pedidos.append(chave)
            while len(self._pedidos) > 60:
                self._pendentes.discard(self._pedidos.popleft())
            self._aviso.notify()

    def ocupada(self):
        """Ainda há pedaço DA TELA esperando o preparo?"""
        return bool(self._pendentes)

    # ------------------------------------------------------------------------
    def _descobrir_versao(self):
        """O endereço dos tiles muda a cada atualização dos dados (as versões
        velhas saem do ar depois de um tempo)."""
        self._t_descoberta = time.time()
        try:
            self._url = rede.baixar_json(TILEJSON, timeout=15)["tiles"][0]
        except Exception as e:
            print("[mapa] usando a versao conhecida dos tiles:", e)

    def _versao_saiu_do_ar(self):
        """Tile não encontrado (404) ou o app abriu sem internet: a versão
        guardada pode ser velha. Consulta de novo (sem exagero)."""
        with self._trava:
            if time.time() - self._t_descoberta < REDESCOBRIR_S:
                return
            self._t_descoberta = time.time()
        self._descobrir_versao()

    def fechar(self):
        """O mapa foi remontado (troca de tema): esta fonte para de trabalhar e
        solta a memória dos tiles."""
        with self._trava:
            self._fechada = True
            self._pedidos.clear()
            self._adiantados.clear()
            self._aviso.notify_all()
        self._prontos.clear()
        self._decodificados.clear()

    def _trabalhar(self):
        while True:
            with self._trava:
                while not self._pedidos and not self._adiantados and not self._fechada:
                    self._aviso.wait()
                if self._fechada:
                    return
                if self._pedidos:
                    chave = self._pedidos.pop()   # o mais recente (o que está na tela) primeiro
                else:
                    chave = self._adiantados.pop()
                    if chave in self._prontos or chave in self._pendentes:
                        continue
                    self._pendentes.add(chave)
            try:
                preparado = self._preparar(chave)
            except Exception as e:
                print("[mapa] tile", chave, e)
                preparado = None
            with self._trava:
                self._pendentes.discard(chave)
                if preparado is None:
                    self._falhas[chave] = time.time()
            if preparado is not None:
                Clock.schedule_once(lambda dt, c=chave, p=preparado: self._entregar(c, p))

    def _entregar(self, chave, preparado):
        self._prontos[chave] = preparado
        while len(self._prontos) > MAX_PREPARADOS:
            self._prontos.popitem(last=False)
        self.ao_ficar_pronto(chave)

    def _caminho_pronto(self, chave):
        dz, tx, ty, rz = chave
        return os.path.join(self._pasta_prontos, str(rz), "%d_%d_%d.bin" % (dz, tx, ty))

    def _preparar(self, chave):
        dz, tx, ty, rz = chave
        caminho = self._caminho_pronto(chave)
        try:   # já foi desenhado uma vez neste celular: vem pronto do disco
            with open(caminho, "rb") as f:
                pronto = desempacotar(f.read(), rz)
            try:
                os.utime(caminho)   # usado agora: é dos últimos a sair quando o disco enche
            except OSError:
                pass
            self.lidos_do_disco += 1
            return pronto
        except OSError:
            pass
        except Exception as e:   # arquivo estragado: prepara de novo e grava por cima
            print("[mapa] pronto estragado:", type(e).__name__)
        dados = pronto_do_app(chave)   # veio desenhado dentro do APK
        if dados is not None:
            try:
                pronto = desempacotar(dados, rz)
                self.lidos_do_app += 1
                return pronto
            except Exception as e:
                print("[mapa] pronto do app estragado:", type(e).__name__)
        pronto = self._preparar_do_zero(chave)
        if pronto is not None and pronto.get("ok"):
            self._gravar(caminho, empacotar(pronto))
        return pronto

    def _preparar_do_zero(self, chave):
        dz, tx, ty, rz = chave
        self.preparados_agora += 1
        n = 2 ** dz
        base = (dz, tx % n, ty)
        camadas = self._decodificados.get(base)
        if camadas is None:
            dados = self._ler_ou_baixar(*base)
            if dados is None:
                return None
            camadas = mvt.ler(dados, ("landuse", "park", "landcover", "water", "building",
                                      "transportation", "transportation_name", "place", "poi"),
                              respirar=_respirar)
            with self._trava:
                self._decodificados[base] = camadas
                while len(self._decodificados) > MAX_DECODIFICADOS:
                    self._decodificados.popitem(last=False)
        return preparar(camadas, dz, tx, ty, rz, self.origem, self.escala, self.densidade)

    def _caminho(self, z, x, y):
        return os.path.join(self.pasta, str(z), str(x), "%d.pbf" % y)

    def _ler_ou_baixar(self, z, x, y):
        dados = do_pacote(z, x, y)   # Goiânia já vem no app: na hora e sem internet
        if dados is not None:
            return dados
        caminho = self._caminho(z, x, y)
        try:
            if time.time() - os.path.getmtime(caminho) < VALIDADE_S:
                with open(caminho, "rb") as f:
                    return f.read()
        except OSError:
            pass
        try:
            dados = rede.baixar(self._url.format(z=z, x=x, y=y), timeout=20)
        except Exception as e:
            if isinstance(e, urllib.error.HTTPError) and e.code in (403, 404, 410):
                url_velha = self._url
                self._versao_saiu_do_ar()
                if self._url != url_velha:
                    try:
                        dados = rede.baixar(self._url.format(z=z, x=x, y=y), timeout=20)
                        return self._gravar(caminho, dados)
                    except Exception:
                        pass
            try:  # sem internet: o velho do disco serve
                with open(caminho, "rb") as f:
                    return f.read()
            except OSError:
                return None
        return self._gravar(caminho, dados)

    def _gravar(self, caminho, dados):
        try:
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
            temporario = "%s.%d.tmp" % (caminho, threading.get_ident())
            with open(temporario, "wb") as f:
                f.write(dados)
            os.replace(temporario, caminho)
        except OSError:
            pass
        return dados

    def _limpar_disco(self):
        try:
            arquivos = []
            for raiz, _, nomes in os.walk(self.pasta):
                for n in nomes:
                    c = os.path.join(raiz, n)
                    st = os.stat(c)
                    arquivos.append((st.st_mtime, st.st_size, c))
            total, limite = sum(a[1] for a in arquivos), LIMITE_DISCO_MB * 1024 * 1024
            for _, tamanho, c in sorted(arquivos):
                if total <= limite:
                    break
                os.remove(c)
                total -= tamanho
        except OSError:
            pass
