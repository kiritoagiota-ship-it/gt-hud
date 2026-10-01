"""Voz do assistente.

No celular, a voz é a do motor de voz do Android (java/.../Fala.java),
falando a FRASE INTEIRA de uma vez (fluida), com o efeito estilo assistente
de IA por cima; a pessoa escolhe a voz e o tom nos Ajustes.

Sem motor de voz em português (e no PC), cai nas falas gravadas (voz/*.wav,
geradas por ferramentas/gerar_voz.py): os pedaços são emendados num WAV só.

Nos dois casos a fila é a mesma: prioridade (curva na hora passa na frente
de aviso) e falas velhas são descartadas (aviso atrasado confunde).
"""
import os
import time
import wave

from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.utils import platform

import falas

PASTA_VOZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voz")
RESPIRO_S = 0.09
VALIDADE_NA_FILA_S = 7.0
ESPERA_MOTOR_S = 4.0     # ao abrir o app, espera o motor de voz ficar pronto
RITMO = 0.95             # um pouco mais pausada: soa mais "assistente"
FRASE_TESTE = ("Sistemas online, senhor. Em duzentos metros, vire à direita. "
               "Subida de oito por cento à frente.")


class Voz:
    def __init__(self, pasta_cache):
        self.ligada = True
        self._pasta = os.path.join(pasta_cache, "falas")
        os.makedirs(self._pasta, exist_ok=True)
        self._fila = []            # [(prioridade, hora, pedaços, texto)]
        self._livre_em = 0.0       # time.monotonic() em que a fala atual termina
        self._som = None           # referência viva do som gravado tocando
        self._ev = None
        self._t_inicio = time.monotonic()
        self._config = None
        self._config_aplicada = False
        self._fala = None          # classe Java Fala (motor do celular)
        if platform == "android":
            try:
                from jnius import autoclass
                self._fala = autoclass("org.kirito.gthud.Fala")
                self._fala.iniciar(autoclass("org.kivy.android.PythonActivity").mActivity)
            except Exception as e:
                print("[voz] sem motor de voz do celular:", e)
                self._fala = None

    # --- motor de voz do celular --------------------------------------------
    def motor_pronto(self):
        return self._fala is not None and self._fala.estado == 1

    def _motor_iniciando(self):
        return (self._fala is not None and self._fala.estado == 0
                and time.monotonic() - self._t_inicio < ESPERA_MOTOR_S)

    def nomes_vozes(self):
        if not self.motor_pronto():
            return []
        return [n for n in self._fala.nomesVozes.split("\n") if n]

    def configurar(self, indice, tom, efeito):
        """Guarda a escolha (Ajustes) e aplica já ou assim que o motor ligar."""
        self._config = (int(indice), float(tom), bool(efeito))
        self._config_aplicada = False
        self._aplicar_config()

    def _aplicar_config(self):
        if self._config_aplicada or not self.motor_pronto() or self._config is None:
            return
        indice, tom, efeito = self._config
        if indice >= 0:
            self._fala.escolherVoz(indice)
        self._fala.ajustar(tom, RITMO, efeito)
        self._config_aplicada = True

    # --- fila ----------------------------------------------------------------
    def falar(self, pedacos, prioridade=1, texto=None):
        """pedacos: chaves de falas.FALAS (usadas pela voz gravada e para
        montar a frase); texto: frase pronta, só para o motor do celular."""
        if not self.ligada:
            return
        pedacos = [p for p in pedacos if p in falas.FALAS]
        if not pedacos and not texto:
            return
        if any(f[2] == pedacos and f[3] == texto for f in self._fila):
            return
        self._fila.append((prioridade, time.monotonic(), pedacos, texto))
        self._fila.sort(key=lambda f: (-f[0], f[1]))
        self._tentar()

    def testar(self):
        self.falar(["bem_vindo"], 3, texto=FRASE_TESTE)

    def calar(self):
        self._fila.clear()
        if self._som is not None:
            self._som.stop()
        if self._fala is not None:
            self._fala.parar()
        self._livre_em = 0.0

    # ------------------------------------------------------------------------
    def _agendar(self, espera):
        if self._ev is None:
            self._ev = Clock.schedule_once(self._liberou, espera)

    def _liberou(self, dt):
        self._ev = None
        self._tentar()

    def _tentar(self, *a):
        agora = time.monotonic()
        if agora < self._livre_em or (self._fala is not None and self._fala.ocupada):
            self._agendar(max(0.15, self._livre_em - agora))
            return
        if self._motor_iniciando():
            self._agendar(0.3)
            return
        self._fila = [f for f in self._fila if agora - f[1] < VALIDADE_NA_FILA_S]
        if not self._fila:
            return
        _, _, pedacos, texto = self._fila.pop(0)
        if self.motor_pronto():
            self._aplicar_config()
            frase = texto or falas.frase(pedacos)
            if self._fala.falar(frase):
                self._livre_em = agora + 0.3  # depois, "ocupada" diz quando terminou
                self._agendar(0.3)
                return
        self._tocar_gravada([p for p in pedacos if os.path.exists(self._arquivo(p))], agora)

    def _tocar_gravada(self, pedacos, agora):
        if not pedacos:
            self._agendar(0.05)
            return
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
        self._agendar(duracao + 0.3)

    def _arquivo(self, chave):
        return os.path.join(PASTA_VOZ, chave + ".wav")

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
