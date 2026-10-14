"""O ouvido do Umbra: o reconhecimento de voz do Android (java/.../Escuta.java, o do Google).

Uma escuta por vez: ouvir() começa, e quem usa confere situacao() até ela terminar. No PC
(e nos testes) não há microfone: as frases "ditas" entram por dizer(texto) e a escuta
termina na hora com elas.
"""
import time

from kivy.utils import platform

import diagnostico

ETAPA = "umbra_escuta"       # (diagnostico.etapa) o reconhecimento de voz do Android rodando
OUVINDO, ENTENDEU, NADA, PARADA, SEM = "ouvindo", "entendeu", "nada", "parada", "sem"
_DO_JAVA = {0: PARADA, 1: OUVINDO, 2: ENTENDEU, 3: NADA, -1: SEM}
# os erros do SpeechRecognizer do Android (para o diagnóstico)
ERROS = {1: "rede lenta", 2: "rede", 3: "áudio", 4: "servidor", 5: "cliente", 6: "silêncio", 7: "nada parecido",
         8: "ocupado", 9: "sem permissão", 10: "pedidos demais", 11: "servidor desconectou", 12: "idioma não suportado",
         13: "idioma indisponível", -2: "não abriu"}
ERRO_IDIOMA_NAO_SUPORTADO, ERRO_IDIOMA_INDISPONIVEL = 12, 13


class Escuta:
    def __init__(self):
        self._java = None
        self._atividade = None
        self._pc_fila = []          # PC/testes: o que vai ser "dito" nas próximas escutas
        self._pc_estado = PARADA
        self._pc_texto = []
        self._pc_ate = 0.0
        self._em_curso = False      # uma escuta do Android começou e ainda não terminou
        self._avisou_nome = False
        self._disponivel = False
        self._disponivel_ate = 0.0
        self.offline_ok = True      # o reconhecimento no próprio celular funciona aqui (para o nome)
        self._offline_agora = False
        self.erros = 0              # erros do reconhecedor seguidos (vão para o diagnóstico)
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
        agora = time.monotonic()
        if agora < self._disponivel_ate:     # (o Umbra pergunta 10 vezes por segundo: o Android, a cada 30 s)
            return self._disponivel
        try:
            self._disponivel = bool(self._java.disponivel(self._atividade))
        except Exception:
            self._disponivel = False
        self._disponivel_ate = agora + 30.0
        return self._disponivel

    def ouvir(self, silencio_s=1.2, conversa=True, offline=None):
        """offline: prefere o reconhecimento no próprio celular (padrão: só para o nome, não para
        o pedido, que o online entende melhor)."""
        if offline is None:
            offline = not conversa and self.offline_ok
        self._offline_agora = offline
        if self._java is not None:
            # etapa arriscada: se o app cair aqui (reconhecimento de voz), na próxima vez a escuta fica desligada
            diagnostico.etapa(ETAPA)
            self._em_curso = True
            if conversa:
                print("[escuta] ouvindo o pedido", flush=True)
            elif not self._avisou_nome:
                self._avisou_nome = True
                print("[escuta] escutando o nome (moto parada)", flush=True)
            try:
                self._java.ouvir(self._atividade, int(silencio_s * 1000), bool(offline))
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

    def _terminou(self):
        if self._em_curso:
            self._em_curso = False
            diagnostico.etapa_ok(ETAPA)

    def parar(self):
        self._terminou()
        if self._java is not None:
            try:
                self._java.parar()
            except Exception:
                pass
        self._pc_estado = PARADA

    def desligar(self):
        self._terminou()
        if self._java is not None:
            try:
                self._java.desligar()
            except Exception:
                pass

    def situacao(self):
        """OUVINDO, ENTENDEU (o texto está em alternativas()), NADA (silêncio ou não entendeu),
        PARADA ou SEM (o celular não tem reconhecimento de voz)."""
        if self._java is not None:
            sit = _DO_JAVA.get(int(self._java.estado), PARADA)
            if sit != OUVINDO and self._em_curso:
                self._terminou()
                erro = int(self._java.erro)
                if sit in (NADA, SEM) and erro not in (0, 6, 7):
                    self.erros += 1
                    print("[escuta] o reconhecimento de voz devolveu o erro %d (%s)%s" % (
                        erro, ERROS.get(erro, "?"), " no modo sem internet" if self._offline_agora else ""), flush=True)
                    if self._offline_agora and erro in (ERRO_IDIOMA_NAO_SUPORTADO, ERRO_IDIOMA_INDISPONIVEL, 5):
                        self.offline_ok = False      # sem o pacote de português no celular: segue online
                        print("[escuta] sem reconhecimento offline em português: usando o online", flush=True)
                else:
                    self.erros = 0
            return sit
        if self._pc_estado == OUVINDO and self._pc_fila:     # "falou" com a escuta já aberta: ouve na hora
            self._pc_texto = [self._pc_fila.pop(0)]
            self._pc_estado = ENTENDEU if self._pc_texto[0] else NADA
        elif self._pc_estado == OUVINDO and time.monotonic() > self._pc_ate:
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
