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


if __name__ == "__main__":
    unittest.main()
