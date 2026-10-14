"""O ouvido do Umbra: o reconhecimento de voz do Android (java/.../Escuta.java, o do Google).

Uma escuta por vez: ouvir() começa, e quem usa confere situacao() até ela terminar. No PC
(e nos testes) não há microfone: as frases "ditas" entram por dizer(texto) e a escuta
termina na hora com elas.
"""
import time

from kivy.utils import platform

OUVINDO, ENTENDEU, NADA, PARADA, SEM = "ouvindo", "entendeu", "nada", "parada", "sem"
_DO_JAVA = {0: PARADA, 1: OUVINDO, 2: ENTENDEU, 3: NADA, -1: SEM}


class Escuta:
    def __init__(self):
        self._java = None
        self._atividade = None
        self._pc_fila = []          # PC/testes: o que vai ser "dito" nas próximas escutas
        self._pc_estado = PARADA
        self._pc_texto = []
        self._pc_ate = 0.0
        if platform == "android":
            try:
                from jnius import autoclass
                self._java = autoclass("org.kirito.gthud.Escuta")
                self._atividade = autoclass("org.kivy.android.PythonActivity").mActivity
            except Exception as e:
                print("[escuta] sem reconhecimento de voz:", e)
                self._java = None

    @property
    def no_android(self):
        return self._java is not None

    def disponivel(self):
        if self._java is None:
            return platform != "android"     # no PC a escuta é simulada
        try:
            return bool(self._java.disponivel(self._atividade))
        except Exception:
            return False

    def ouvir(self, silencio_s=1.2):
        if self._java is not None:
            try:
                self._java.ouvir(self._atividade, int(silencio_s * 1000))
            except Exception as e:
                print("[escuta]", e)
            return
        if self._pc_fila:
            self._pc_texto = [self._pc_fila.pop(0)]
            self._pc_estado = ENTENDEU if self._pc_texto[0] else NADA
        else:
            self._pc_texto = []
            self._pc_estado = OUVINDO
            self._pc_ate = time.monotonic() + 4.0    # no PC, sem nada para dizer, a escuta "acaba" sozinha

    def parar(self):
        if self._java is not None:
            try:
                self._java.parar()
            except Exception:
                pass
        self._pc_estado = PARADA

    def desligar(self):
        if self._java is not None:
            try:
                self._java.desligar()
            except Exception:
                pass

    def situacao(self):
        """OUVINDO, ENTENDEU (o texto está em alternativas()), NADA (silêncio ou não entendeu),
        PARADA ou SEM (o celular não tem reconhecimento de voz)."""
        if self._java is not None:
            return _DO_JAVA.get(int(self._java.estado), PARADA)
        if self._pc_estado == OUVINDO and time.monotonic() > self._pc_ate:
            self._pc_estado = NADA
        return self._pc_estado

    def alternativas(self):
        """O que foi dito: as alternativas do reconhecedor, da mais provável para a menos."""
        if self._java is not None:
            return [t for t in str(self._java.texto).split("\n") if t.strip()]
        return list(self._pc_texto)

    def parcial(self):
        return str(self._java.parcial) if self._java is not None else ""

    def nivel(self):
        """Volume da voz de quem está falando agora (0 a 1)."""
        try:
            return float(self._java.nivel) if self._java is not None else 0.0
        except Exception:
            return 0.0

    def erro(self):
        return int(self._java.erro) if self._java is not None else 0

    # --- PC e testes --------------------------------------------------------------
    def dizer(self, texto):
        """Põe uma frase na fila do que vai ser "dito" (texto vazio = silêncio)."""
        self._pc_fila.append(texto)
