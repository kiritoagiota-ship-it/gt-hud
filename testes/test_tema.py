"""Tema claro/escuro pelo horário e cores trocadas no lugar."""
import time
import unittest

import mapa_vetor
import tema


def hora(h, m=0, mes=10, dia=7):
    return time.localtime(time.mktime((2026, mes, dia, h, m, 0, 0, 0, -1)))


class TesteTema(unittest.TestCase):
    def tearDown(self):
        tema.aplicar("escuro")
        mapa_vetor.aplicar_tema(False)

    def test_nascer_e_por_do_sol_em_goiania(self):
        nascer, por = tema.sol(-16.68, -49.25, hora(12))
        self.assertTrue(5 * 60 + 30 < nascer < 6 * 60 + 30, nascer)     # ~5h54 em outubro
        self.assertTrue(17 * 60 + 45 < por < 18 * 60 + 45, por)          # ~18h14
        inverno = tema.sol(-16.68, -49.25, hora(12, mes=6, dia=21))
        verao = tema.sol(-16.68, -49.25, hora(12, mes=12, dia=21))
        self.assertLess(inverno[1] - inverno[0], verao[1] - verao[0])   # dia mais curto em junho

    def test_claro_de_dia_escuro_de_noite(self):
        for h, m, esperado in ((0, 0, "escuro"), (5, 30, "escuro"), (6, 30, "claro"), (12, 0, "claro"),
                               (17, 30, "claro"), (18, 30, "escuro"), (23, 0, "escuro")):
            self.assertEqual(tema.modo_pela_hora(-16.68, -49.25, hora(h, m)), esperado, (h, m))

    def test_cores_trocam_no_lugar(self):
        ciano, fundo = tema.CIANO, tema.FUNDO           # referências guardadas (como os widgets fazem)
        escuro = list(ciano)
        tema.aplicar("claro")
        self.assertIs(tema.CIANO, ciano)
        self.assertNotEqual(list(ciano), escuro)
        self.assertGreater(sum(fundo[:3]), 2.4)         # fundo claro
        self.assertLess(sum(tema.BRANCO[:3]), 0.6)      # texto escuro
        self.assertTrue(tema.claro())
        tema.aplicar("escuro")
        self.assertEqual(list(ciano), escuro)
        tema.aplicar("coisa")                           # nome estranho: escuro
        self.assertEqual(tema.modo, "escuro")

    def test_mapa_troca_e_volta(self):
        fundo, rua = mapa_vetor.FUNDO, mapa_vetor.RUAS["rua"]
        antes = (tuple(fundo), rua, dict(mapa_vetor.AREAS))
        mapa_vetor.aplicar_tema(True)
        self.assertIs(mapa_vetor.FUNDO, fundo)
        self.assertGreater(sum(fundo[:3]), 2.4)
        self.assertEqual(mapa_vetor.RUAS["rua"][1][:3], (1.0, 1.0, 1.0))
        self.assertEqual(mapa_vetor.RUAS["rua"][0], rua[0])             # largura e zoom não mudam
        # de longe a rua some para o fundo (não para o preto)
        longe = mapa_vetor.cor_rua("rua", 13)
        self.assertTrue(fundo[0] < longe[0] < 1.0)
        mapa_vetor.aplicar_tema(False)
        self.assertEqual((tuple(fundo), mapa_vetor.RUAS["rua"], dict(mapa_vetor.AREAS)), antes)


if __name__ == "__main__":
    unittest.main()
