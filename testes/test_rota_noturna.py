"""Rota noturna (pelas ruas principais) e o que o app diz das rotas à noite."""
import time
import unittest

import rota as rotas
import tema
from testes.apoio import rota_reta

GOIANIA = (-16.68, -49.25)


def _hora(h, m=0):
    return time.struct_time((2026, 10, 7, h, m, 0, 2, 280, 0))


class TesteNoite(unittest.TestCase):
    def test_e_noite_pelo_sol_de_goiania(self):
        # (struct_time sem fuso: tema.sol usa o fuso do aparelho; aqui só horas folgadas, longe do nascer/pôr)
        nascer, por = tema.sol(GOIANIA[0], GOIANIA[1], _hora(12))
        meio_dia = _hora(int((nascer + por) // 2 // 60))
        self.assertFalse(tema.e_noite(GOIANIA[0], GOIANIA[1], meio_dia))
        depois = int(por // 60 + 2) % 24
        self.assertTrue(tema.e_noite(GOIANIA[0], GOIANIA[1], _hora(depois)))
        antes = int(nascer // 60 - 2) % 24
        self.assertTrue(tema.e_noite(GOIANIA[0], GOIANIA[1], _hora(antes)))

    def test_noturna_fica_na_lista_com_o_nome_dela(self):
        rapida = rota_reta(3000, tempo_s=600)
        noturna = rota_reta(3400, tempo_s=700)
        noturna.perfil, noturna.nome_perfil = "noturna", rotas.NOME_NOTURNA
        lista = rotas.rotular([noturna, rapida])
        self.assertEqual([r.nome_perfil for r in lista], ["Mais rápida", "Noturna (ruas principais)"])

    def test_opcoes_sao_o_contrario_da_tranquila(self):
        tranquila = dict((p[0], p[2]) for p in rotas.PERFIS)["tranquila"]
        self.assertEqual((rotas.OPCOES_NOTURNA["use_roads"], tranquila["use_roads"]), (1.0, 0.0))

    def test_so_pede_a_noturna_de_noite(self):
        pedidos = []
        real_principal, real_sleep, real_medir = rotas._pedir_principal, rotas.time.sleep, rotas.medir_movimento

        def principal(origem, destino, rumo, nome, perfil, alternativas=0, evitar=()):
            pedidos.append(perfil)
            r = rota_reta(3000 + 400 * len(pedidos), tempo_s=600 + 60 * len(pedidos), lon0=-49.25 + 0.002 * len(pedidos))
            r.perfil = perfil
            return [r] if alternativas else r
        rotas._pedir_principal = principal
        rotas.time.sleep = lambda s: None
        rotas.medir_movimento = lambda r: None
        try:
            base = rota_reta(3000, tempo_s=600)
            rotas.pedir_alternativas(GOIANIA, (-16.70, -49.27), ja=[base], voltas=0, noite=False)
            self.assertNotIn("noturna", pedidos)
            del pedidos[:]
            lista = rotas.pedir_alternativas(GOIANIA, (-16.70, -49.27), ja=[base], voltas=0, noite=True)
            self.assertEqual(pedidos[0], "noturna")
            self.assertEqual(lista[-1].nome_perfil, "Noturna (ruas principais)")
        finally:
            rotas._pedir_principal, rotas.time.sleep, rotas.medir_movimento = real_principal, real_sleep, real_medir


if __name__ == "__main__":
    unittest.main()
