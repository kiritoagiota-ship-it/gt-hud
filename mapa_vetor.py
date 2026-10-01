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

Coordenadas "locais": pixels do Web Mercator no zoom 14, menos uma origem
fixa, com Y para cima (como no Kivy).
"""
import collections
import math
import os
import threading
import time

from kivy.clock import Clock
from kivy.graphics.tesselator import TYPE_POLYGONS, WINDING_ODD, Tesselator

import mvt
import rede

TILEJSON = "https://tiles.openfreemap.org/planet"
URL_PADRAO = "https://tiles.openfreemap.org/planet/20260927_080001_pt/{z}/{x}/{y}.pbf"
Z_DADOS_MAX = 14
VALIDADE_S = 30 * 86400
TRABALHADORES = 2
MAX_PREPARADOS = 64
MAX_DECODIFICADOS = 24
LIMITE_DISCO_MB = 200
MAX_VERTICES_MESH = 60000  # índices do Mesh são de 16 bits

# --- estilo (cores RGBA; larguras em dp no zoom 16) ---------------------------
FUNDO = (0.016, 0.027, 0.043, 1)
AREAS = {
    "residencial": (0.030, 0.045, 0.062, 1),
    "verde": (0.030, 0.115, 0.085, 1),
    "agua": (0.025, 0.115, 0.205, 1),
    "predio": (0.060, 0.088, 0.118, 1),
}
# (largura dp no z16, cor, zoom mínimo)
RUAS = collections.OrderedDict([
    ("servico", (2.2, (0.22, 0.27, 0.33, 1), 15)),
    ("caminho", (1.8, (0.20, 0.26, 0.30, 1), 15)),
    ("ciclovia", (2.6, (0.20, 0.66, 0.46, 1), 14)),
    ("rua", (4.0, (0.36, 0.42, 0.49, 1), 13)),
    ("terciaria", (5.2, (0.50, 0.56, 0.63, 1), 12)),
    ("secundaria", (6.2, (0.60, 0.66, 0.73, 1), 10)),
    ("primaria", (6.8, (0.67, 0.72, 0.79, 1), 8)),
    ("expressa", (7.6, (0.78, 0.82, 0.88, 1), 6)),
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
_POI_IGNORAR = {"bus", "railway", "toilets", "atm", "bench", "waste_basket", "parking",
                "bicycle_parking", "post", "telephone", "vending", "recycling"}


def cor_rua(nome, rz):
    """De longe, ruas pequenas mais apagadas (senão viram uma teia que
    compete com as avenidas e com a rota)."""
    r, g, b, a = RUAS[nome][1]
    if nome in ("rua", "servico", "caminho") and rz <= 14:
        f = 0.62 if rz <= 13 else 0.75
        return (r * f, g * f, b * f, a)
    return RUAS[nome][1]


def z_dados(rz):
    return max(0, min(Z_DADOS_MAX, rz))


def tiles_do_retangulo(x0, y0, x1, y1, dz):
    """Tiles do zoom de dados dz que cobrem o retângulo em px do mundo z14."""
    lado = 256.0 * 2 ** (14 - dz)
    n = 2 ** dz
    tx0, tx1 = int(math.floor(x0 / lado)), int(math.floor(x1 / lado))
    ty0, ty1 = max(0, int(math.floor(y0 / lado))), min(n - 1, int(math.floor(y1 / lado)))
    return [(tx, ty) for tx in range(tx0, tx1 + 1) for ty in range(ty0, ty1 + 1)]


# --- geometria ------------------------------------------------------------------
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
    """Acumula triângulos e corta em pedaços de até MAX_VERTICES_MESH."""

    def __init__(self):
        self.pedacos = [([], [])]

    def _atual(self, novos):
        v, i = self.pedacos[-1]
        if len(v) // 4 + novos > MAX_VERTICES_MESH:
            self.pedacos.append(([], []))
        return self.pedacos[-1]

    def leque(self, cx, cy, r, lados=7):
        v, ind = self._atual(lados + 1)
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
        v, ind = self._atual(len(pts) * 4)
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
        v, ind = self._atual(len(vertices) // 4)
        base = len(v) // 4
        v += vertices
        for k in range(1, len(indices_leque) - 1):
            ind += [base + indices_leque[0], base + indices_leque[k], base + indices_leque[k + 1]]

    def listas(self):
        return [(v, i) for v, i in self.pedacos if i]


def preparar(camadas, dz, tx, ty, rz, origem, escala, densidade):
    """Geometria pronta (listas) do tile para desenhar no zoom rz."""
    lado = 256.0 * 2 ** (14 - dz)
    ox, oy = origem
    px_por_local = escala * 2.0 ** (rz - 14)          # px da tela por unidade local

    def conversor(extent):
        k = lado / extent
        bx, by = tx * lado - ox, oy - ty * lado

        def conv(p):
            return (bx + p[0] * k, by - p[1] * k)
        return conv

    tol2 = (0.6 / px_por_local) ** 2                   # simplifica abaixo de ~0,6 px
    areas = {nome: _Malha() for nome in AREAS}
    tess_ok = True

    def area(nome_cor, partes, conv):
        nonlocal tess_ok
        tess = Tesselator()
        for parte in partes:
            pts = _simplificar([conv(p) for p in parte], tol2)
            if len(pts) >= 3:
                tess.add_contour([c for p in pts for c in p])
        try:
            if not tess.tesselate(WINDING_ODD, TYPE_POLYGONS):
                return
        except Exception:
            tess_ok = False
            return
        for vertices, indices in tess.meshes:
            areas[nome_cor].triangulos(list(vertices), list(indices))

    for nome_camada, alvo in (("landuse", None), ("park", "verde"), ("landcover", "verde"),
                              ("water", "agua"), ("building", "predio")):
        if nome_camada not in camadas or (nome_camada == "building" and rz < 16):
            continue
        extent, feicoes = camadas[nome_camada]
        conv = conversor(extent)
        for tipo, props, partes in feicoes:
            if tipo != 3:
                continue
            cor = alvo
            if nome_camada == "landuse":
                classe = props.get("class")
                cor = "residencial" if classe in ("residential", "suburb", "neighbourhood") else (
                    "verde" if classe in ("cemetery", "pitch", "playground", "stadium") else None)
            elif nome_camada == "landcover" and props.get("class") not in ("grass", "wood", "farmland", "scrub"):
                continue
            if cor:
                area(cor, partes, conv)

    ruas = {nome: _Malha() for nome in RUAS}
    rotulos = []
    if "transportation" in camadas:
        extent, feicoes = camadas["transportation"]
        conv = conversor(extent)
        for tipo, props, partes in feicoes:
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
            for parte in partes:
                pts = _simplificar([conv(p) for p in parte], tol2)
                ruas[estilo].faixa(pts, meia, lados)
    if "transportation_name" in camadas and rz >= 14:
        extent, feicoes = camadas["transportation_name"]
        conv = conversor(extent)
        for tipo, props, partes in feicoes:
            nome = props.get("name")
            if tipo != 2 or not nome:
                continue
            estilo = _CLASSE_RUA.get(props.get("class"), "rua")
            if rz < RUAS.get(estilo, (0, 0, 13))[2] + 1:
                continue
            for parte in partes:
                pts = [conv(p) for p in parte]
                if len(pts) < 2:
                    continue
                # trecho mais longo e reto da parte: onde o nome cabe melhor
                melhor = max(range(len(pts) - 1),
                             key=lambda k: math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]))
                (ax, ay), (bx, by) = pts[melhor], pts[melhor + 1]
                rotulos.append({"texto": nome, "x": (ax + bx) / 2, "y": (ay + by) / 2,
                                "ang": math.atan2(by - ay, bx - ax),
                                "comp": math.hypot(bx - ax, by - ay),
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
            x, y = conv(partes[0][0])
            rotulos.append({"texto": nome, "x": x, "y": y, "ang": 0.0, "comp": 0,
                            "peso": 9 if classe in ("city", "town") else 8, "tipo": "lugar"})
    if "poi" in camadas and rz >= 15:
        extent, feicoes = camadas["poi"]
        conv = conversor(extent)
        for tipo, props, partes in feicoes:
            nome = props.get("name")
            if (tipo != 1 or not nome or props.get("rank", 99) > (12 if rz >= 17 else 5)
                    or props.get("class") in _POI_IGNORAR or props.get("subclass") == "bus_stop"
                    or nome.strip().isdigit()):
                continue
            x, y = conv(partes[0][0])
            rotulos.append({"texto": nome, "x": x, "y": y, "ang": 0.0, "comp": 0,
                            "peso": 0.5 - props.get("rank", 99) / 100.0, "tipo": "poi"})
    return {
        "areas": [(nome, m.listas()) for nome, m in areas.items()],
        "ruas": [(nome, cor_rua(nome, rz), m.listas()) for nome, m in ruas.items()],
        "rotulos": rotulos,
        "ok": tess_ok,
    }


# --- download, cache e fila de preparo ------------------------------------------
class FonteVetorial:
    def __init__(self, pasta, origem, escala, densidade, ao_ficar_pronto):
        self.pasta = os.path.join(pasta, "vetor")
        os.makedirs(self.pasta, exist_ok=True)
        self.origem, self.escala, self.densidade = origem, escala, densidade
        self.ao_ficar_pronto = ao_ficar_pronto   # chamada na thread do Kivy com a chave
        self._url = URL_PADRAO
        self._prontos = collections.OrderedDict()       # (dz, tx, ty, rz) -> preparado
        self._decodificados = collections.OrderedDict()  # (dz, tx, ty) -> camadas
        self._pedidos = collections.deque()
        self._pendentes = set()
        self._falhas = {}
        self._trava = threading.Lock()
        self._aviso = threading.Condition(self._trava)
        threading.Thread(target=self._descobrir_versao, daemon=True).start()
        for _ in range(TRABALHADORES):
            threading.Thread(target=self._trabalhar, daemon=True).start()
        threading.Thread(target=self._limpar_disco, daemon=True).start()

    def pronto(self, chave):
        p = self._prontos.get(chave)
        if p is not None:
            self._prontos.move_to_end(chave)
        return p

    def pedir(self, chave):
        """Pede o preparo do tile (dz, tx, ty, rz) se ainda não tem."""
        if chave in self._prontos:
            return
        with self._trava:
            if chave in self._pendentes or time.time() - self._falhas.get(chave, 0) < 15:
                return
            self._pendentes.add(chave)
            self._pedidos.append(chave)
            while len(self._pedidos) > 60:
                self._pendentes.discard(self._pedidos.popleft())
            self._aviso.notify()

    # ------------------------------------------------------------------------
    def _descobrir_versao(self):
        """O endereço dos tiles muda a cada atualização dos dados."""
        try:
            self._url = rede.baixar_json(TILEJSON, timeout=15)["tiles"][0]
        except Exception as e:
            print("[mapa] usando a versao conhecida dos tiles:", e)

    def _trabalhar(self):
        while True:
            with self._trava:
                while not self._pedidos:
                    self._aviso.wait()
                chave = self._pedidos.pop()   # o mais recente (o que está na tela) primeiro
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

    def _preparar(self, chave):
        dz, tx, ty, rz = chave
        n = 2 ** dz
        base = (dz, tx % n, ty)
        camadas = self._decodificados.get(base)
        if camadas is None:
            dados = self._ler_ou_baixar(*base)
            if dados is None:
                return None
            camadas = mvt.ler(dados, ("landuse", "park", "landcover", "water", "building",
                                      "transportation", "transportation_name", "place", "poi"))
            with self._trava:
                self._decodificados[base] = camadas
                while len(self._decodificados) > MAX_DECODIFICADOS:
                    self._decodificados.popitem(last=False)
        return preparar(camadas, dz, tx, ty, rz, self.origem, self.escala, self.densidade)

    def _caminho(self, z, x, y):
        return os.path.join(self.pasta, str(z), str(x), "%d.pbf" % y)

    def _ler_ou_baixar(self, z, x, y):
        caminho = self._caminho(z, x, y)
        try:
            if time.time() - os.path.getmtime(caminho) < VALIDADE_S:
                with open(caminho, "rb") as f:
                    return f.read()
        except OSError:
            pass
        try:
            dados = rede.baixar(self._url.format(z=z, x=x, y=y), timeout=20)
        except Exception:
            try:  # sem internet: o velho do disco serve
                with open(caminho, "rb") as f:
                    return f.read()
            except OSError:
                return None
        try:
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
            temporario = caminho + ".tmp"
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
