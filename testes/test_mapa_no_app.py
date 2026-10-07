"""O mapa de Goiânia que vem dentro do app (dados/goiania_mapa.db)."""
import unittest

import mapa_vetor
import mvt
import rede


class TesteMapaNoApp(unittest.TestCase):
    def test_goiania_inteira_esta_no_pacote(self):
        todos = mapa_vetor.FonteVetorial.tiles_goiania()
        self.assertEqual(mapa_vetor.partes_no_pacote(), len(todos))
        self.assertEqual([t for t in todos if mapa_vetor.do_pacote(*t) is None], [])

    def test_os_pedacos_abrem(self):
        z14 = mapa_vetor.FonteVetorial.tiles_goiania((14,))
        for z, x, y in z14[::37]:
            camadas = mvt.ler(mapa_vetor.do_pacote(z, x, y), ("transportation", "water", "landuse"))
            self.assertIsInstance(camadas, dict)
        centro = max(z14, key=lambda t: len(mapa_vetor.do_pacote(*t)))     # o pedaço mais cheio: o centro
        self.assertGreater(len(mvt.ler(mapa_vetor.do_pacote(*centro), ("transportation",))["transportation"][1]), 200)

    def test_fora_de_goiania_nao_esta(self):
        self.assertIsNone(mapa_vetor.do_pacote(14, 0, 0))

    def test_ler_um_pedaco_de_goiania_nao_usa_a_internet(self):
        def sem_rede(url, timeout=20):
            raise AssertionError("foi à internet: " + url)
        original = rede.baixar
        rede.baixar = sem_rede
        try:
            z, x, y = mapa_vetor.FonteVetorial.tiles_goiania((13,))[40]
            fonte = mapa_vetor.FonteVetorial.__new__(mapa_vetor.FonteVetorial)     # sem threads nem pasta
            self.assertEqual(fonte._ler_ou_baixar(z, x, y), mapa_vetor.do_pacote(z, x, y))
        finally:
            rede.baixar = original


if __name__ == "__main__":
    unittest.main()
