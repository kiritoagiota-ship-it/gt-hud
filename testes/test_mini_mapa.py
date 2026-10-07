"""Ruas de perto para o mini mapa do painel flutuante."""
import unittest

import mini_mapa
import segundo_plano
from segundo_plano import SegundoPlano
from testes.test_segundo_plano import AndroidFalso, AppFalso

AQUI = (-16.6800, -49.2550)


def _grau(metros):
    return metros / mini_mapa.GRAU_M


class TesteMiniMapa(unittest.TestCase):
    def setUp(self):
        mini_mapa._tiles.clear()
        tile = mini_mapa.tile_de(*AQUI)
        lat, lon = AQUI
        # uma avenida leste-oeste passando 50 m ao norte e uma rua bem longe (3 km)
        avenida = [(lat + _grau(50), lon + _grau(d) / 0.958) for d in range(-900, 901, 3)]
        longe = [(lat + _grau(3000), lon), (lat + _grau(3100), lon)]
        mini_mapa._tiles[tile] = [(3, avenida), (1, longe)]

    def tearDown(self):
        mini_mapa._tiles.clear()

    def _ler(self, z, x, y):
        return None     # (os tiles do teste já estão guardados; os vizinhos não existem)

    def test_so_as_ruas_de_perto_em_metros_da_ancora(self):
        ruas = mini_mapa.ruas_perto(self._ler, AQUI[0], AQUI[1], AQUI)
        self.assertEqual(len(ruas), 1)                          # a rua a 3 km ficou de fora
        grossura, pontos = ruas[0]
        self.assertEqual(grossura, 3)
        self.assertTrue(all(abs(y - 50) < 2 for _, y in pontos))            # 50 m ao norte da âncora
        self.assertTrue(min(x for x, _ in pontos) >= -mini_mapa.RAIO_M - 1)
        self.assertTrue(max(x for x, _ in pontos) <= mini_mapa.RAIO_M + 1)   # cortada no raio
        passos = [b[0] - a[0] for a, b in zip(pontos, pontos[1:])]
        self.assertTrue(all(p >= mini_mapa.JUNTAR_M - 0.5 for p in passos))  # pontos colados foram juntados

    def test_texto_para_o_painel(self):
        self.assertEqual(mini_mapa.em_texto([(2, [(0.4, -10.6), (12.0, 3.2)]), (1, [(5, 5), (6, 7)])]),
                         "2:0,-11 12,3;1:5,5 6,7")
        self.assertEqual(mini_mapa.em_texto([]), "")

    def test_ancora_diferente_muda_as_coordenadas(self):
        outra = (AQUI[0] - _grau(100), AQUI[1])
        _, pontos = mini_mapa.ruas_perto(self._ler, AQUI[0], AQUI[1], outra)[0]
        self.assertTrue(all(abs(y - 150) < 2 for _, y in pontos))            # 50 + 100 m ao norte da âncora

    def test_o_painel_recebe_as_ruas_na_mesma_ancora_da_rota(self):
        import time
        from navegacao import Navegacao
        from testes.apoio import Fala, rota_reta
        rota = rota_reta(600, lat0=AQUI[0], lon0=AQUI[1])
        app, android = AppFalso(), AndroidFalso()
        app.ajustes["flutuante_tipo"] = "painel"
        app.nav = Navegacao(rota, Fala())
        app.nav.atualizar(rota.pontos[5][0], rota.pontos[5][1], 20.0, 1.0)
        app.estado_nav = None
        fundo = SegundoPlano(app, android)
        fundo._ler_tile = self._ler
        fundo.minimizado = fundo._painel_a_vista = True
        fundo._cuidar_das_ruas()                                 # define a âncora e manda buscar as ruas
        self.assertIsNotNone(fundo._ancora)
        fim = time.time() + 3
        while fundo._ruas_prontas is None and time.time() < fim:
            time.sleep(0.02)
        fundo._cuidar_das_ruas()                                 # as ruas ficaram prontas: vão para o painel
        enviadas = [c for c in android.chamadas if c[0] == "ruas_painel" and c[1]]
        self.assertEqual(len(enviadas), 1)
        self.assertTrue(enviadas[0][1].startswith("3:"))
        # a rota vai na mesma âncora: a pessoa (50 m depois do começo) está a ~0 m dela
        texto, inicio, aqui = segundo_plano.desenho_da_rota(app.nav, fundo._ancora)
        pontos = [tuple(map(float, p.split(","))) for p in texto.split(";")]
        perto = min(abs(y) for _, y in pontos)
        self.assertLess(perto, 6)
        fundo.minimizado = False


if __name__ == "__main__":
    unittest.main()
