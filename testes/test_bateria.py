"""Km rodados desde a última carga da moto, as barrinhas e a autonomia estimada."""
import unittest

import caminhos  # noqa: F401
import bateria
from bateria import Bateria

GRAU_POR_M = 1.0 / 111320.0   # 1 metro para o norte, em graus de latitude


class _Ajustes(dict):
    def __init__(self):
        super().__init__(bateria=None, bateria_cargas=[])
        self.gravacoes = 0

    def __setitem__(self, chave, valor):
        self.gravacoes += 1
        super().__setitem__(chave, valor)


def andar(bat, metros, kmh=40.0, t0=0.0, lat0=-16.68):
    """Anda `metros` para o norte a `kmh`, uma leitura por segundo. Devolve (t, lat) do fim."""
    passo = kmh / 3.6
    n = int(round(metros / passo))
    for k in range(n + 1):
        bat.registrar(lat0 + k * passo * GRAU_POR_M, -49.25, kmh, t0 + k)
    return t0 + n, lat0 + n * passo * GRAU_POR_M


class TesteBateria(unittest.TestCase):
    def setUp(self):
        self.agora = [1000.0]
        self.aj = _Ajustes()
        self.bat = Bateria(self.aj, relogio=lambda: self.agora[0])

    def test_so_conta_depois_de_marcar_a_carga(self):
        andar(self.bat, 500)
        self.assertFalse(self.bat.ativa)
        self.assertEqual(self.bat.texto_curto(), "Bateria")
        self.bat.carregou()
        andar(self.bat, 2000)
        self.assertAlmostEqual(self.bat.metros, 2000, delta=30)
        self.assertEqual(self.bat.texto_curto(), "5/5  2,0 km")
        self.assertAlmostEqual(self.bat.vel_media_kmh, 40, delta=1)

    def test_parado_e_salto_do_gps_nao_contam(self):
        self.bat.carregou()
        t, lat = andar(self.bat, 300)
        antes = self.bat.metros
        for k in range(1, 20):                                   # parado no semáforo, GPS tremendo
            self.bat.registrar(lat + (k % 2) * 3 * GRAU_POR_M, -49.25, 0.5, t + k)
        self.assertEqual(self.bat.metros, antes)
        self.bat.registrar(lat + 800 * GRAU_POR_M, -49.25, 40.0, t + 21)   # pulo de 800 m em 2 s
        self.assertEqual(self.bat.metros, antes)
        self.bat.registrar(lat + 900 * GRAU_POR_M, -49.25, 40.0, t + 600)  # app ficou fechado 10 min
        self.assertEqual(self.bat.metros, antes)

    def test_barrinhas_e_quanto_cada_uma_durou(self):
        self.bat.carregou()
        t, lat = andar(self.bat, 9000)
        self.assertTrue(self.bat.caiu_barra())
        andar(self.bat, 7000, t0=t + 1, lat0=lat)
        self.bat.caiu_barra()
        self.assertEqual(self.bat.barras, 3)
        duracoes = self.bat.km_por_barra()
        self.assertAlmostEqual(duracoes[0], 9000, delta=60)
        self.assertAlmostEqual(duracoes[1], 7000, delta=60)
        self.assertAlmostEqual(self.bat.autonomia_m(), 16000 / 2 * 5, delta=300)   # sem histórico: pelas barrinhas
        self.assertIn("3 de 5", self.bat.texto())
        self.assertTrue(self.bat.desfazer_barra())
        self.assertEqual(self.bat.barras, 4)
        for _ in range(9):
            self.bat.caiu_barra()
        self.assertEqual(self.bat.barras, 0)                      # nunca passa de 5 quedas
        self.assertFalse(self.bat.caiu_barra())

    def test_recarregar_guarda_a_carga_e_ensina_a_autonomia(self):
        self.assertIsNone(self.bat.autonomia_m())
        self.bat.carregou()
        andar(self.bat, 24000)
        self.agora[0] = 5000.0
        self.bat.carregou(sobra=2)                               # gastou 3 barrinhas em 24 km
        cargas = self.aj["bateria_cargas"]
        self.assertEqual(len(cargas), 1)
        self.assertEqual(cargas[0]["sobra"], 2)
        self.assertAlmostEqual(cargas[0]["m"], 24000, delta=100)
        self.assertEqual(self.bat.metros, 0.0)
        self.assertEqual(self.bat.barras, 5)
        self.assertAlmostEqual(self.bat.autonomia_m(), 40000, delta=300)
        self.assertIn("uns 40 km", self.bat.texto())
        self.assertIn("sobraram 2 de 5", self.bat.texto_historico())
        self.bat.carregou(sobra=5)                               # toque repetido: carga de 0 km não entra
        self.assertEqual(len(self.aj["bateria_cargas"]), 1)

    def test_grava_aos_poucos_e_continua_depois_de_fechar(self):
        self.bat.carregou()
        antes = self.aj.gravacoes
        t, lat = andar(self.bat, 1000)
        self.assertLessEqual(self.aj.gravacoes - antes, 1000 / bateria.GRAVAR_A_CADA_M + 1)
        self.bat.caiu_barra()
        self.bat.guardar()
        outra = Bateria(self.aj)                                 # o app abriu de novo
        self.assertAlmostEqual(outra.metros, self.bat.metros)
        self.assertEqual(outra.barras, 4)
        andar(outra, 500, t0=0.0, lat0=lat)
        self.assertAlmostEqual(outra.metros, 1500, delta=40)


if __name__ == "__main__":
    unittest.main()
