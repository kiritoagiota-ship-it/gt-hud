import unittest
from array import array

import mapa_vetor
import mvt


class TesteMvt(unittest.TestCase):
    def test_geometria_do_exemplo_da_especificacao(self):
        # exemplos da especificação Mapbox Vector Tile 2.1
        self.assertEqual([list(p) for p in mvt._geometria([9, 50, 34])], [[25, 17]])
        poligono = mvt._geometria([9, 6, 12, 18, 10, 12, 24, 44, 15])
        self.assertEqual(list(poligono[0]), [3, 6, 8, 12, 20, 34, 3, 6])  # fechado
        self.assertIsInstance(poligono[0], array)  # array, não tuplas (coletor de lixo)


class TesteGeometria(unittest.TestCase):
    def test_poligonos_e_furos(self):
        externo = [(0, 0), (10, 0), (10, 10), (0, 10)]
        furo = [(2, 2), (2, 4), (4, 4), (4, 2)]
        outro = [(20, 0), (30, 0), (30, 10), (20, 10)]
        aneis = [(a, mapa_vetor._area2(a)) for a in (externo, furo, outro)]
        polis = mapa_vetor._poligonos(aneis)
        self.assertEqual(len(polis), 2)          # 2 prédios
        self.assertEqual(len(polis[0]), 2)       # o 1º com o furo
        self.assertTrue(mapa_vetor._convexo(externo))
        self.assertFalse(mapa_vetor._convexo([(0, 0), (10, 0), (5, 2), (10, 10), (0, 10)]))

    def test_preparar_predios_ruas_e_nomes(self):
        quadrado = lambda x, y, l: array("i", [x, y, x + l, y, x + l, y + l, x, y + l, x, y])
        camadas = {
            "building": (4096, [(3, {}, [quadrado(100, 100, 50), quadrado(300, 300, 80)])]),
            "transportation": (4096, [(2, {"class": "primary"}, [array("i", [0, 2000, 4096, 2000])])]),
            "transportation_name": (4096, [(2, {"class": "primary", "name": "Avenida Goiás"},
                                            [array("i", [0, 2000, 4096, 2000])])]),
        }
        r = mapa_vetor.preparar(camadas, 14, 0, 0, 17, (0, 0), 2.6, 2.6)
        predios = dict(r["areas"])["predio"]
        self.assertGreater(sum(len(i) for _, i in predios), 0)
        ruas = {nome: listas for nome, _, listas in r["ruas"]}
        self.assertTrue(ruas["primaria"])
        self.assertEqual([x["texto"] for x in r["rotulos"]], ["Avenida Goiás"])
        self.assertTrue(r["grade"])

    def test_tiles_de_goiania(self):
        tiles = mapa_vetor.FonteVetorial.tiles_goiania()
        self.assertEqual(len(tiles), len(set(tiles)))
        self.assertTrue(400 < len(tiles) < 600, len(tiles))


if __name__ == "__main__":
    unittest.main()
