"""Pedaços do mapa (tiles 256x256 do OpenStreetMap): baixa, guarda em disco
e transforma em textura para o widget do mapa.

Regras de uso do tile.openstreetmap.org, seguidas aqui: User-Agent
identificado (rede.py), no máximo 2 downloads ao mesmo tempo, cache local
(30 dias) e nada de baixar em massa. Para um app pessoal é uso leve.
Sem internet, serve o que já estiver no disco (mesmo vencido).
"""
import collections
import io
import os
import threading
import time

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage

import rede

URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
VALIDADE_S = 30 * 86400
MAX_TEXTURAS = 120         # ~30 MB de textura; a tela usa umas 40-60
MAX_PEDIDOS = 90           # pedidos velhos (o mapa já andou) são descartados
TRABALHADORES = 2          # regra do OpenStreetMap: no máximo 2 conexões
LIMITE_DISCO_MB = 150
ESPERA_APOS_FALHA_S = 20


class Tiles:
    def __init__(self, pasta, ao_chegar):
        self.pasta = os.path.join(pasta, "tiles")
        os.makedirs(self.pasta, exist_ok=True)
        self.ao_chegar = ao_chegar  # ao_chegar((z, x, y)) na thread do Kivy
        self._texturas = collections.OrderedDict()  # LRU: (z, x, y) -> textura
        self._pedidos = collections.deque()          # o mais novo é atendido primeiro
        self._pendentes = set()
        self._falhas = {}
        self._trava = threading.Lock()
        self._aviso = threading.Condition(self._trava)
        for _ in range(TRABALHADORES):
            threading.Thread(target=self._trabalhar, daemon=True).start()
        threading.Thread(target=self._limpar_disco, daemon=True).start()

    # --- chamado pelo mapa (thread do Kivy) -------------------------------
    def textura(self, z, x, y):
        """Textura do tile se já estiver pronta; senão pede e devolve None."""
        chave = (z, x, y)
        tex = self._texturas.get(chave)
        if tex is not None:
            self._texturas.move_to_end(chave)
            return tex
        with self._trava:
            if (chave not in self._pendentes
                    and time.time() - self._falhas.get(chave, 0) > ESPERA_APOS_FALHA_S):
                self._pendentes.add(chave)
                self._pedidos.append(chave)
                while len(self._pedidos) > MAX_PEDIDOS:
                    self._pendentes.discard(self._pedidos.popleft())
                self._aviso.notify()
        return None

    # --- threads de download ----------------------------------------------
    def _trabalhar(self):
        while True:
            with self._trava:
                while not self._pedidos:
                    self._aviso.wait()
                chave = self._pedidos.pop()
            dados = self._ler_ou_baixar(*chave)
            if dados is None:
                with self._trava:
                    self._pendentes.discard(chave)
                    self._falhas[chave] = time.time()
                continue
            Clock.schedule_once(lambda dt, c=chave, d=dados: self._criar_textura(c, d))

    def _caminho(self, z, x, y):
        return os.path.join(self.pasta, str(z), str(x), "%d.png" % y)

    def _ler_ou_baixar(self, z, x, y):
        caminho = self._caminho(z, x, y)
        try:
            if time.time() - os.path.getmtime(caminho) < VALIDADE_S:
                with open(caminho, "rb") as f:
                    return f.read()
        except OSError:
            pass
        try:
            dados = rede.baixar(URL.format(z=z, x=x, y=y), timeout=15)
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
        """Mantém o cache abaixo de LIMITE_DISCO_MB apagando os mais antigos."""
        try:
            arquivos = []
            for raiz, _, nomes in os.walk(self.pasta):
                for n in nomes:
                    c = os.path.join(raiz, n)
                    st = os.stat(c)
                    arquivos.append((st.st_mtime, st.st_size, c))
            total = sum(a[1] for a in arquivos)
            limite = LIMITE_DISCO_MB * 1024 * 1024
            for _, tamanho, c in sorted(arquivos):
                if total <= limite:
                    break
                os.remove(c)
                total -= tamanho
        except OSError:
            pass

    # --- de volta na thread do Kivy ---------------------------------------
    def _criar_textura(self, chave, dados):
        with self._trava:
            self._pendentes.discard(chave)
        try:
            tex = CoreImage(io.BytesIO(dados), ext="png", nocache=True).texture
        except Exception as e:
            print("[tiles] imagem ruim", chave, e)
            return
        self._texturas[chave] = tex
        while len(self._texturas) > MAX_TEXTURAS:
            self._texturas.popitem(last=False)
        self.ao_chegar(chave)
