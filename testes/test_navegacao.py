import unittest

from navegacao import Navegacao
from testes.apoio import M_GRAU, Fala, manobra, rota_reta


def andar(nav, rota, ate_m, passo_m=10, vel_kmh=20.0, t0=0.0):
    lat0, lon0 = rota.pontos[0]
    estado = None
    for k, d in enumerate(range(0, ate_m + 1, passo_m)):
        estado = nav.atualizar(lat0 + d / M_GRAU, lon0, vel_kmh, t0 + k)
    return estado


class TesteNavegacao(unittest.TestCase):
    def test_curvas_coladas_logo_depois_e_chegada(self):
        r = rota_reta(600, manobras=[manobra("em_frente", 0), manobra("direita", 40),
                                     manobra("esquerda", 47), manobra("chegada", 60)])
        fala = Fala()
        nav = Navegacao(r, fala)
        nav.alertas = []  # sem semáforos da cidade no meio do teste
        andar(nav, r, 600)
        textos = fala.textos()
        self.assertTrue(any("E logo depois, vire à esquerda" in t for t in textos), textos)
        self.assertIn("Senhor, você chegou ao destino.", textos)
        self.assertTrue(nav.chegou)

    def test_seta_anda_em_cima_da_rota(self):
        r = rota_reta(600)
        nav = Navegacao(r, Fala())
        lat0, lon0 = r.pontos[0]
        nav.atualizar(lat0 + 100 / M_GRAU, lon0 + 5 / M_GRAU, 36.0, 0)  # 5 m ao lado
        lat, lon, _ = nav.prever(1.0)                                    # 10 m/s por 1 s
        self.assertAlmostEqual((lat - lat0) * M_GRAU, 110, delta=2)
        self.assertAlmostEqual(lon, lon0, places=6)                      # na linha
        nav.atualizar(lat0 + 100 / M_GRAU, lon0 + 40 / M_GRAU, 36.0, 1)  # longe da linha
        self.assertIsNone(nav.prever(1.0))

    def test_semaforo_no_maximo_1_a_cada_400_m_e_lombada_sempre(self):
        r = rota_reta(1500)
        fala = Fala()
        nav = Navegacao(r, fala)
        nav.alertas = [(d, "semaforo") for d in (200, 300, 400, 700)] + [(500, "lombada")]
        nav.alertas.sort()
        andar(nav, r, 1500)
        textos = fala.textos()
        self.assertEqual(textos.count("Semáforo à frente."), 2, textos)  # 200 e 700
        self.assertEqual(textos.count("Lombada à frente, reduza."), 1)

    def test_semaforos_desligados(self):
        r = rota_reta(800)
        fala = Fala()
        nav = Navegacao(r, fala, avisar_semaforos=False)
        nav.alertas = [(300, "semaforo"), (500, "lombada")]
        andar(nav, r, 800)
        self.assertNotIn("Semáforo à frente.", fala.textos())
        self.assertIn("Lombada à frente, reduza.", fala.textos())

    def test_descida_leve_nao_fala_forte_fala(self):
        e = [800.0] * 6 + [800 - 1.2 * k for k in range(1, 11)] + [788.0] * 6 \
            + [788 - 2.4 * k for k in range(1, 11)] + [764.0] * 6
        r = rota_reta(len(e) * 30 - 30, elevacao=e)
        fala = Fala()
        nav = Navegacao(r, fala)
        nav.alertas = []
        andar(nav, r, len(e) * 30 - 60)
        descidas = [t for t in fala.textos() if "descida" in t]
        self.assertEqual(len(descidas), 1, descidas)       # só a forte (8%, medida ~7%)
        self.assertNotIn("quatro por cento", descidas[0])

    def test_fora_da_rota_pede_recalculo(self):
        r = rota_reta(800)
        nav = Navegacao(r, Fala())
        lat0, lon0 = r.pontos[0]
        for k in range(8):
            nav.atualizar(lat0 + (100 + k * 5) / M_GRAU, lon0 + 50 / M_GRAU, 15.0, float(k))
        self.assertTrue(nav.recalcular_pedido)



class TesteViagem(unittest.TestCase):
    def test_salto_do_gps_nao_infla_distancia_nem_media(self):
        from viagem import Viagem
        relogio = [0.0]
        v = Viagem(relogio=lambda: relogio[0])
        v.iniciar()
        lat = -16.68
        for k in range(10):          # 20 km/h = 5,6 m/s, 1 leitura por segundo
            relogio[0] = float(k)
            salto = 40 / M_GRAU if k == 5 else 0.0   # GPS pula 40 m numa leitura
            v.registrar(lat + k * 5.6 / M_GRAU + salto, -49.25, 20.0)
        self.assertLess(v.distancia_m, 9 * 5.6 * 1.5 + 30)
        self.assertLessEqual(v.vel_media_kmh, v.vel_max_kmh)

if __name__ == "__main__":
    unittest.main()
