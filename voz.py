"""Voz do assistente: junta falas prontas (voz/<chave>.wav, geradas no PC por
ferramentas/gerar_voz.py) numa frase só e toca, uma de cada vez.

Juntar os pedaços num WAV único (com um respiro curto entre eles) evita
buraco e sobreposição entre pedaços. A fila tem prioridade (curva na hora
passa na frente de aviso) e descarta falas velhas: aviso atrasado confunde.
"""
import os
import time
import wave

from kivy.clock import Clock
from kivy.core.audio import SoundLoader

PASTA_VOZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voz")
RESPIRO_S = 0.09
VALIDADE_NA_FILA_S = 7.0


class Voz:
    def __init__(self, pasta_cache):
        self.ligada = True
        self._pasta = os.path.join(pasta_cache, "falas")
        os.makedirs(self._pasta, exist_ok=True)
        self._fila = []            # [(prioridade, hora, pedaços)]
        self._livre_em = 0.0       # time.monotonic() em que a fala atual termina
        self._som = None           # referência viva do som tocando
        self._ev = None

    def falar(self, pedacos, prioridade=1):
        if not self.ligada:
            return
        pedacos = [p for p in pedacos if os.path.exists(self._arquivo(p))]
        if not pedacos or any(f[2] == pedacos for f in self._fila):
            return
        self._fila.append((prioridade, time.monotonic(), pedacos))
        self._fila.sort(key=lambda f: (-f[0], f[1]))
        self._tentar()

    def calar(self):
        self._fila.clear()
        if self._som is not None:
            self._som.stop()
        self._livre_em = 0.0

    # ------------------------------------------------------------------------
    def _arquivo(self, chave):
        return os.path.join(PASTA_VOZ, chave + ".wav")

    def _tentar(self, *a):
        agora = time.monotonic()
        if agora < self._livre_em:
            if self._ev is None:
                self._ev = Clock.schedule_once(self._liberou, self._livre_em - agora)
            return
        self._fila = [f for f in self._fila if agora - f[1] < VALIDADE_NA_FILA_S]
        if not self._fila:
            return
        _, _, pedacos = self._fila.pop(0)
        try:
            caminho, duracao = self._montar(pedacos)
            som = SoundLoader.load(caminho)
        except Exception as e:
            print("[voz]", e)
            return
        if som is None:
            return
        self._som = som
        som.play()
        self._livre_em = agora + duracao + 0.25
        if self._ev is None:
            self._ev = Clock.schedule_once(self._liberou, duracao + 0.3)

    def _liberou(self, dt):
        self._ev = None
        self._tentar()

    def _montar(self, pedacos):
        """WAV com os pedaços emendados (fica guardado: a mesma frase repete muito)."""
        caminho = os.path.join(self._pasta, "-".join(pedacos) + ".wav")
        if os.path.exists(caminho):
            with wave.open(caminho, "rb") as w:
                return caminho, w.getnframes() / float(w.getframerate())
        quadros, params = [], None
        for p in pedacos:
            with wave.open(self._arquivo(p), "rb") as w:
                params = params or w.getparams()
                quadros.append(w.readframes(w.getnframes()))
        respiro = b"\x00" * (int(params.framerate * RESPIRO_S) * params.sampwidth * params.nchannels)
        temporario = caminho + ".tmp"
        with wave.open(temporario, "wb") as w:
            w.setparams(params)
            w.writeframes(respiro.join(quadros))
        os.replace(temporario, caminho)
        total = sum(len(q) for q in quadros) + len(respiro) * (len(quadros) - 1)
        return caminho, total / float(params.framerate * params.sampwidth * params.nchannels)
