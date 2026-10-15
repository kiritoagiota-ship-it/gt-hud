"""O movimento do rosto do Umbra fica estável a qualquer velocidade de tela.

Achado em 14/10/2026: a conta da "mola" divergia a 30 quadros/s (o olhar ia a 1e38, a cabeça virava
junto e o desenho estourava em branco). O celular cai para 30 quadros/s quando esquenta ou economiza
bateria, então isso tem de valer de 15 a 120.
"""
import math
import random
import unittest

import caminhos  # noqa: F401
from widgets.rosto_umbra import ALVOS, Movimento


class TesteMovimento(unittest.TestCase):
    def test_estavel_em_qualquer_velocidade_de_tela(self):
        for fps in (15, 30, 60, 120):
            mov = Movimento(sorteio=random.Random(3))
            dt = 1.0 / fps
            estados = list(ALVOS)
            t = 0.0
            maior = 0.0
            for i in range(int(20 * fps)):
                if i % int(1.5 * fps) == 0:
                    mov.mudar(estados[(i // int(1.5 * fps)) % len(estados)], t)
                voz = max(0.0, math.sin(t * 9.0))
                u = mov.quadro(t, dt, voz, 0.5)
                for k, v in u.items():
                    for x in (v if isinstance(v, tuple) else (v,)):
                        self.assertTrue(math.isfinite(x), "%s não é número a %d quadros/s" % (k, fps))
                        maior = max(maior, abs(x))
                t += dt
            self.assertLess(maior, 5.0, "algum valor escapou a %d quadros/s (%.3g)" % (fps, maior))

    def test_olhar_e_cabeca_ficam_no_tamanho_certo_a_30_quadros(self):
        mov = Movimento(sorteio=random.Random(5))
        t, dt = 0.0, 1.0 / 30
        giros, olhares = [], []
        for _ in range(int(30 * 30)):
            u = mov.quadro(t, dt, 0.0)
            giros.append(abs(u["giro"][0]))
            olhares.append(abs(u["olhar"][0]))
            t += dt
        self.assertLess(max(giros), 1.0)            # a cabeça só vira um pouco
        self.assertLess(max(olhares), 1.2)          # e o olhar fica dentro do olho (antes ia a 1e38)

    def test_dentes_crescem_quando_ele_se_anima(self):
        def dentes(estado, voz=0.0, segundos=2.0):
            mov = Movimento(sorteio=random.Random(2))
            t, dt = 0.0, 1.0 / 60
            mov.quadro(t, dt, 0.0)
            mov.mudar(estado, t)
            u = None
            for _ in range(int(segundos / dt)):
                u = mov.quadro(t, dt, voz)
                t += dt
            return u["dentes"]
        self.assertLess(dentes("parado"), 0.05)
        self.assertGreater(dentes("alerta"), 0.85)               # ameaçando: dentes no máximo
        self.assertGreater(dentes("confirmou"), 0.45)            # contente: sorrisão
        self.assertGreater(dentes("falando", voz=0.95), 0.40)    # falando forte: crescem com a ênfase

    def test_mordida_no_fim_da_silaba(self):
        mov = Movimento(sorteio=random.Random(4))
        t, dt = 0.0, 1.0 / 60
        mov.quadro(t, dt, 0.0)
        mov.mudar("falando", t)
        bocas = []
        for i in range(int(1.2 / dt)):
            voz = 0.9 if i < int(0.4 / dt) else 0.0               # uma sílaba forte e depois silêncio
            bocas.append(mov.quadro(t, dt, voz)["boca"])
            t += dt
        fim_da_silaba = int(0.4 / dt)
        self.assertGreater(max(bocas), 0.6)                         # abriu
        self.assertLess(min(bocas[fim_da_silaba:]), -0.02)          # fechou passando um tiquinho: os dentes batem
        self.assertGreaterEqual(min(bocas), -0.10)                  # sem exagero
        self.assertAlmostEqual(bocas[-1], 0.0, delta=0.02)          # e assentou


class TesteExpressoes(unittest.TestCase):
    """Expressões novas (pedido do dono, 15/10/2026)."""

    def _depois(self, estado, segundos=1.5, nivel=0.0, mov=None):
        mov = mov or Movimento(sorteio=random.Random(2))
        t, dt = 0.0, 1.0 / 60
        mov.quadro(t, dt, 0.0)
        mov.mudar(estado, t)
        u = None
        for _ in range(int(segundos / dt)):
            u = mov.quadro(t, dt, 0.0, nivel)
            t += dt
        return u

    def test_estados_novos_existem(self):
        for estado in ("irritado", "pensando"):
            self.assertIn(estado, ALVOS)

    def test_irritado_fecha_a_cara(self):
        parado, irritado = self._depois("parado"), self._depois("irritado")
        self.assertGreater(irritado["inclina"], parado["inclina"] + 0.4)   # sobrancelha baixa
        self.assertLess(irritado["olho"], parado["olho"] - 0.15)          # olhos estreitos
        self.assertGreater(irritado["dentes"], 0.4)                        # rosnado leve

    def test_contente_semicerra_os_olhos(self):
        self.assertGreaterEqual(self._depois("confirmou")["palpebra"], 0.25)

    def test_ouvindo_reage_a_voz(self):
        quieto = self._depois("ouvindo", nivel=0.0)
        falando = self._depois("ouvindo", nivel=1.0)
        self.assertGreater(falando["olho"], quieto["olho"] + 0.1)        # os olhos abrem com a sua voz
        self.assertGreater(falando["boca"], quieto["boca"] + 0.05)       # a boca entreabre

    def test_pensando_olha_para_cima(self):
        self.assertLess(self._depois("pensando")["olhar"][1], -0.3)

    def test_acordar_abre_os_olhos_de_uma_vez(self):
        mov = Movimento(sorteio=random.Random(2))
        t, dt = 1.0, 1.0 / 60
        mov.quadro(t, dt, 0.0)
        mov.acordar(t)
        fechado = mov.quadro(t + dt, dt, 0.0)["palpebra"]
        aberto = mov.quadro(t + 0.3, dt, 0.0)["palpebra"]
        self.assertGreater(fechado, 0.9)
        self.assertLess(aberto, 0.2)

    def test_rosto_acompanha_a_fala(self):
        # nas palavras fortes a sobrancelha desce, os olhos se estreitam e brilham (dono, 15/10/2026)
        def falando(voz):
            mov = Movimento(sorteio=random.Random(2))
            t, dt = 0.0, 1.0 / 60
            mov.quadro(t, dt, 0.0)
            mov.mudar("falando", t)
            u = None
            for _ in range(int(1.0 / dt)):
                u = mov.quadro(t, dt, voz)
                t += dt
            return u
        fraca, forte = falando(0.40), falando(0.95)
        self.assertGreater(forte["inclina"], fraca["inclina"] + 0.2)
        self.assertLess(forte["olho"], fraca["olho"] - 0.05)
        self.assertGreater(forte["brilho"], fraca["brilho"] + 0.1)

    def test_alerta_treme_a_cabeca_no_susto(self):
        mov = Movimento(sorteio=random.Random(2))
        t, dt = 0.0, 1.0 / 60
        mov.quadro(t, dt, 0.0)
        mov.mudar("alerta", t)
        giros = []
        for _ in range(int(0.5 / dt)):
            giros.append(mov.quadro(t, dt, 0.0)["giro"][0])
            t += dt
        trocas = sum(1 for a, b, c in zip(giros, giros[1:], giros[2:]) if (b - a) * (c - b) < 0)
        self.assertGreater(trocas, 6)                                     # tremeu (vai e volta várias vezes)


if __name__ == "__main__":
    unittest.main()
