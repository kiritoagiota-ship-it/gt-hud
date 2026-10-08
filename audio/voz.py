"""Voz do assistente.

No celular, a voz é a do motor de voz do Android (java/.../Fala.java),
falando a FRASE INTEIRA de uma vez (fluida), com o efeito estilo assistente
de IA por cima; a pessoa escolhe a voz e o tom nos Ajustes.

Sem motor de voz em português (e no PC), cai nas falas gravadas (voz/*.wav,
geradas por ferramentas/gerar_voz.py): os pedaços são emendados num WAV só.

Nos dois casos a fila é a mesma: prioridade (curva na hora passa na frente
de aviso) e falas velhas são descartadas (aviso atrasado confunde).
"""
import json
import os
import shutil
import time
import wave

from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.utils import platform

import falas
import sons

PASTA_VOZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voz")
RESPIRO_S = 0.09
ENTRADA_S = 0.3          # silêncio antes da fala gravada: a saída de áudio come o começo
VALIDADE_NA_FILA_S = 7.0
ESPERA_MOTOR_S = 4.0     # ao abrir o app, espera o motor de voz ficar pronto
RITMO = 1.0              # ritmo natural do motor (mais lento soava robótico)
MEDIDA_MAX_S = 40.0      # medição das vozes (masculina automática): desiste depois disso
# o motor de voz às vezes não avisa que terminou (ex.: o sistema matou o
# serviço de voz): passado esse tempo, a fala é cortada e a fila anda
TRAVADA_BASE_S = 6.0
TRAVADA_POR_LETRA_S = 0.12
FRASE_TESTE = ("Sistemas online, senhor. Em duzentos metros, vire à direita. "
               "Subida de oito por cento à frente.")


def marca_da_voz():
    """Um nome curto para a voz que está gravada em audio/voz (de audio/voz/voz.json, que
    quem grava a voz escreve). Muda a voz -> muda a marca."""
    try:
        with open(os.path.join(PASTA_VOZ, "voz.json"), encoding="utf-8") as f:
            d = json.load(f)
        return "".join(c for c in "%s-%s" % (d.get("voz", ""), d.get("feita_em", "")) if c.isalnum() or c == "-")[:48]
    except (OSError, ValueError):
        return "3"      # a voz que veio antes de existir o voz.json (pasta "falas3")


def pasta_das_frases(pasta_cache):
    """Onde ficam as frases já emendadas (a mesma frase repete muito). Uma pasta POR VOZ:
    trocou a voz do app, as frases guardadas da antiga não servem (e são apagadas)."""
    atual = "falas" + marca_da_voz()
    try:
        for nome in os.listdir(pasta_cache):
            velha = os.path.join(pasta_cache, nome)
            if nome.startswith("falas") and nome != atual and os.path.isdir(velha):
                shutil.rmtree(velha, ignore_errors=True)
    except OSError:
        pass
    pasta = os.path.join(pasta_cache, atual)
    os.makedirs(pasta, exist_ok=True)
    return pasta


class Voz:
    def __init__(self, pasta_cache):
        self.ligada = True
        self.sons = None             # sons.Sons: o toque que anuncia cada fala (o app liga)
        self.gravada = True          # True: fala com as gravações do app; False: com a voz do celular
        self._pasta = pasta_das_frases(pasta_cache)
        self._fila = []            # [(prioridade, hora, pedaços, texto)]
        self._livre_em = 0.0       # time.monotonic() em que a fala atual termina
        self._som = None           # referência viva do som gravado tocando
        self._ev = None
        self._t_inicio = time.monotonic()
        self._config = None
        self._config_aplicada = False
        self._fala = None          # classe Java Fala (motor do celular)
        self._limite_fala = 0.0    # time.monotonic() em que a fala atual "travou"
        self._t_medida = None      # medindo as vozes (a fila espera)
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
        if (self._fala is not None and self._t_medida is not None
                and time.monotonic() - self._t_medida < MEDIDA_MAX_S):
            return True  # medindo as vozes: falar agora sairia com uma voz qualquer
        return (self._fala is not None and self._fala.estado == 0
                and time.monotonic() - self._t_inicio < ESPERA_MOTOR_S)

    def medir_vozes(self, ao_terminar):
        """Acha a voz mais GRAVE (masculina) do celular medindo a altura de
        cada uma (Fala.acharVozGrave); ao_terminar(índice ou None)."""
        if not self.motor_pronto():
            ao_terminar(None)
            return
        self._fala.acharVozGrave()
        self._t_medida = time.monotonic()

        def conferir(dt):
            grave = self._fala.vozGrave
            if grave == -1 and time.monotonic() - self._t_medida < MEDIDA_MAX_S:
                return True
            self._t_medida = None
            print("[voz] altura das vozes (indice:Hz):", self._fala.tonsVozes)
            ao_terminar(grave if grave >= 0 else None)
            self._config_aplicada = False
            self._tentar()
            return False
        Clock.schedule_interval(conferir, 0.5)

    def estado_motor(self):
        """"pronto", "iniciando" ou "sem" (sem motor: voz gravada)."""
        if self._fala is None or self._fala.estado == -1:
            return "sem"
        return "pronto" if self._fala.estado == 1 else "iniciando"

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
            if self.sons is not None:   # voz desligada: o toque sozinho ainda avisa
                self.sons.tocar(sons.som_da_fala(pedacos))
            return
        pedacos = [p for p in pedacos if p in falas.FALAS]
        if not pedacos and not texto:
            return
        if any(f[2] == pedacos and f[3] == texto for f in self._fila):
            return
        self._fila.append((prioridade, time.monotonic(), pedacos, texto))
        self._fila.sort(key=lambda f: (-f[0], f[1]))
        self._tentar()

    def bombear(self):
        """Faz a fila andar sem o Clock (app minimizado: segundo_plano.py)."""
        self._tentar()

    def testar(self):
        if self.gravada:   # uma frase montada em pedaços, como na navegação: dá para ouvir a emenda
            self.falar(["senhor", "em_200", "vire_direita"], 3)
        else:
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
        ocupada = self._fala is not None and self._fala.ocupada
        if ocupada and agora > self._limite_fala:
            print("[voz] o motor de voz nao terminou a fala: cortando")
            self._fala.parar()
            ocupada = False
        if agora < self._livre_em or ocupada:
            self._agendar(max(0.15, self._livre_em - agora))
            return
        if not self.gravada and self._motor_iniciando():   # (a voz gravada não espera o motor do celular)
            self._agendar(0.3)
            return
        self._fila = [f for f in self._fila if agora - f[1] < VALIDADE_NA_FILA_S]
        if not self._fila:
            return
        _, _, pedacos, texto = self._fila.pop(0)
        if self.sons is not None:       # o toque do tipo de aviso, logo antes da fala
            self.sons.tocar(sons.som_da_fala(pedacos))
        tem_gravacao = [p for p in pedacos if os.path.exists(self._arquivo(p))]
        # voz do celular: quando ela foi a escolhida, ou quando a frase não tem gravação nenhuma
        # (melhor a outra voz do que ficar mudo)
        if self.motor_pronto() and (not self.gravada or not tem_gravacao):
            self._aplicar_config()
            frase = texto or falas.frase(pedacos)
            if self._fala.falar(frase):
                self._livre_em = agora + 0.3  # depois, "ocupada" diz quando terminou
                self._limite_fala = agora + TRAVADA_BASE_S + TRAVADA_POR_LETRA_S * len(frase)
                self._agendar(0.3)
                return
        self._tocar_gravada(tem_gravacao, agora)

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
        entrada = b"\x00" * (int(params.framerate * ENTRADA_S) * params.sampwidth * params.nchannels)
        temporario = caminho + ".tmp"
        with wave.open(temporario, "wb") as w:
            w.setparams(params)
            w.writeframes(entrada + respiro.join(quadros))
        os.replace(temporario, caminho)
        total = len(entrada) + sum(len(q) for q in quadros) + len(respiro) * (len(quadros) - 1)
        return caminho, total / float(params.framerate * params.sampwidth * params.nchannels)
