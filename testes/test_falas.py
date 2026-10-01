import unittest

import falas


class TesteFalas(unittest.TestCase):
    def test_frase_maiuscula_so_no_comeco_de_frase(self):
        self.assertEqual(falas.frase(["senhor", "em_200", "vire_direita"]),
                         "Senhor, em duzentos metros, vire à direita.")
        self.assertEqual(falas.frase(["rota_calculada", "em_frente"]),
                         "Rota calculada. Vamos lá. Siga em frente.")
        self.assertEqual(falas.frase(["senhor", "gps_perdido"]), "Senhor, perdi o sinal do GPS.")

    def test_logo_depois(self):
        self.assertEqual(falas.frase(["em_100", "vire_direita", "logo_depois", "vire_esquerda"]),
                         "Em cem metros, vire à direita. E logo depois, vire à esquerda.")

    def test_resumo_singular_plural_e_metros(self):
        self.assertIn("600 metros", falas.resumo_rota(600, 120, 0))
        self.assertIn("cerca de 1 minuto.", falas.resumo_rota(1000, 50, 0))
        self.assertIn("1 quilômetro,", falas.resumo_rota(1000, 50, 0))
        self.assertIn("1 hora e 15 minutos", falas.resumo_rota(62000, 4500, 0))
        self.assertIn("com 410 metros de subida", falas.resumo_rota(62000, 4500, 410))
        self.assertNotIn("subida", falas.resumo_rota(5000, 900, 10))

    def test_chaves_existem(self):
        for g in (2, 3, 8, 30):
            self.assertIn(falas.chave_subida(g), falas.FALAS)
            self.assertIn(falas.chave_descida(g), falas.FALAS)
        for acao in ("esquerda", "direita", "chegada", "chegada_direita", "rotatoria", "retorno"):
            self.assertIn(falas.chave_manobra(acao), falas.FALAS)
        self.assertEqual(falas.chave_manobra("rotatoria", 2), "rotatoria_2")
        self.assertEqual(falas.chave_manobra("acao_desconhecida"), "em_frente")

    def test_distancia_falada(self):
        self.assertEqual(falas.distancia_falada(190), 200)
        self.assertEqual(falas.distancia_falada(3000), 2000)


if __name__ == "__main__":
    unittest.main()
