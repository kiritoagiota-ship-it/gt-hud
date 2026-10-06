"""Versão 1.0.22: ritmo do dono no tempo de chegada, servidor de rotas
reserva, gravação da viagem em segundo plano e lugares da busca no mapa."""
import unittest

import busca
import rota as rotas
from ritmo import Ritmo
from segundo_plano import SegundoPlano, textos
from testes.apoio import rota_reta
from testes.test_rota import codificar_polyline
from testes.test_segundo_plano import AndroidFalso, AppFalso
from viagem import Viagem


class NavFalsa:
    def __init__(self, rota):
        self.rota, self.dist_feita, self.dist_da_linha = rota, 0.0, 0.0


class TesteRitmo(unittest.TestCase):
    def tearDown(self):
        rotas.fator_ritmo = 1.0

    def _andar(self, ritmo, nav, vel_ms, segundos, t0=0.0):
        for k in range(1, segundos + 1):
            nav.dist_feita += vel_ms
            ritmo.leitura(nav, vel_ms * 3.6, t0 + k)
        return t0 + segundos

    def test_mais_rapido_que_o_previsto_encurta_o_tempo(self):
        rota = rota_reta(comprimento_m=6000, tempo_s=1200)   # servidor: 5 m/s
        ritmo, nav = Ritmo(1.0), NavFalsa(rota)
        ritmo.leitura(nav, 0, 0.0)
        self._andar(ritmo, nav, 6.25, 400)                    # o dono: 6,25 m/s = 80% do tempo
        self.assertLess(rotas.fator_ritmo, 0.95)              # já corrige durante a viagem
        self.assertLess(rota.tempo_s, 1200)
        aprendido = ritmo.terminar()
        self.assertTrue(0.8 <= aprendido < 0.95)
        self.assertEqual(rotas.fator_ritmo, aprendido)
        for _ in range(8):                                    # várias viagens iguais: converge
            nav = NavFalsa(rota)
            ritmo.leitura(nav, 0, 0.0)
            self._andar(ritmo, nav, 6.25, 800)
            ritmo.terminar()
        self.assertAlmostEqual(ritmo.aprendido, 0.8, delta=0.02)

    def test_parada_longa_nao_conta_e_semaforo_conta(self):
        rota = rota_reta(comprimento_m=6000, tempo_s=1200)
        ritmo, nav = Ritmo(1.0), NavFalsa(rota)
        ritmo.leitura(nav, 0, 0.0)
        t = self._andar(ritmo, nav, 5.0, 300)
        for k in range(1, 601):                               # 10 min parado
            ritmo.leitura(nav, 0.0, t + k)
        self._andar(ritmo, nav, 5.0, 300, t + 600)
        # 600 s andando no previsto + só 40 s da parada
        self.assertAlmostEqual(ritmo._real_s / ritmo._previsto_s, 640 / 600.0, delta=0.01)

    def test_viagem_curta_e_fora_da_rota_nao_ensinam(self):
        rota = rota_reta(comprimento_m=6000, tempo_s=1200)
        ritmo, nav = Ritmo(1.0), NavFalsa(rota)
        ritmo.leitura(nav, 0, 0.0)
        self._andar(ritmo, nav, 10.0, 20)                     # só 20 s
        self.assertEqual(ritmo.terminar(), 1.0)
        nav = NavFalsa(rota)
        nav.dist_da_linha = 80.0                              # fora da rota
        ritmo.leitura(nav, 0, 0.0)
        self._andar(ritmo, nav, 10.0, 400)
        self.assertEqual(ritmo.terminar(), 1.0)

    def test_fator_guardado_estragado_vira_normal(self):
        self.assertEqual(Ritmo("x").aprendido, 1.0)
        self.assertEqual(Ritmo(9).aprendido, 2.0)


class TesteServidorReserva(unittest.TestCase):
    def setUp(self):
        self._principal, self._json = rotas._pedir_principal, rotas.rede.baixar_json

    def tearDown(self):
        rotas._pedir_principal, rotas.rede.baixar_json = self._principal, self._json

    def _osrm(self):
        a, b, b2, c = (-16.68, -49.25), (-16.681, -49.25), (-16.682, -49.25), (-16.682, -49.251)
        passos = [
            {"maneuver": {"type": "depart", "modifier": "right"}, "name": "Rua 1", "geometry": codificar_polyline([a, b])},
            {"maneuver": {"type": "new name", "modifier": "straight"}, "name": "Rua 1A", "geometry": codificar_polyline([b, b2])},
            {"maneuver": {"type": "turn", "modifier": "right"}, "name": "Rua 2", "geometry": codificar_polyline([b2, c])},
            {"maneuver": {"type": "arrive", "modifier": "left"}, "name": "Rua 2", "geometry": codificar_polyline([c, c])},
        ]
        return {"code": "Ok", "routes": [{"geometry": codificar_polyline([a, b, b2, c]), "duration": 100.0,
                                          "legs": [{"steps": passos}]}]}

    def test_principal_fora_do_ar_usa_o_reserva(self):
        def fora(*a):
            raise OSError("servidor fora do ar")
        rotas._pedir_principal = fora
        rotas.rede.baixar_json = lambda url, timeout=20: self._osrm()
        rota = rotas.pedir_rota((-16.68, -49.25), (-16.681, -49.251), destino_nome="Casa")
        self.assertTrue(rota.reserva)
        self.assertEqual([(m["acao"], m["indice"]) for m in rota.manobras],
                         [("em_frente", 0), ("direita", 2), ("chegada_esquerda", 3)])
        self.assertAlmostEqual(rota.tempo_base_s, 100 * rotas.RESERVA_TEMPO)
        self.assertEqual(rota.subidas, [])
        self.assertEqual(rota.destino_nome, "Casa")

    def test_sem_caminho_nao_vai_para_o_reserva(self):
        def sem(*a):
            raise rotas.SemRota("sem caminho")
        rotas._pedir_principal = sem
        rotas.rede.baixar_json = lambda *a, **k: self.fail("não era para chamar o reserva")
        with self.assertRaises(rotas.SemRota):
            rotas.pedir_rota((0, 0), (1, 1))

    def test_os_dois_fora_devolve_o_erro_do_principal(self):
        def fora(*a):
            raise OSError("principal")

        def tambem(*a, **k):
            raise OSError("reserva")
        rotas._pedir_principal, rotas.rede.baixar_json = fora, tambem
        with self.assertRaises(OSError) as c:
            rotas.pedir_rota((0, 0), (1, 1))
        self.assertEqual(str(c.exception), "principal")

    def test_outros_perfis_nao_usam_o_reserva(self):
        def fora(*a):
            raise OSError("principal")
        rotas._pedir_principal = fora
        rotas.rede.baixar_json = lambda *a, **k: self.fail("perfil alternativo não tem reserva")
        with self.assertRaises(OSError):
            rotas.pedir_rota((0, 0), (1, 1), perfil="plana")


class TesteGravarEmSegundoPlano(unittest.TestCase):
    def _app(self):
        app = AppFalso()
        app.nav = None
        app.viagem = Viagem()
        return app

    def test_gravando_sem_rota_liga_o_servico_e_segue_minimizado(self):
        app, android = self._app(), AndroidFalso()
        fundo = SegundoPlano(app, android)
        fundo.sincronizar()
        self.assertEqual(android.chamadas, [])                # nada gravando: nada ligado
        app.viagem.iniciar()
        fundo.sincronizar()
        self.assertIn("iniciar", android.nomes())
        titulo, _, l1, _ = textos(app)
        self.assertTrue(titulo.startswith("Gravando viagem"))
        self.assertEqual(l1, "0 m")
        fundo.ao_pausar()
        self.assertTrue(fundo.minimizado)
        fundo.ao_voltar()
        app.viagem.finalizar()
        fundo.sincronizar()
        self.assertEqual(android.nomes()[-1], "parar")

    def test_pausada_continua_ligado(self):
        app, android = self._app(), AndroidFalso()
        fundo = SegundoPlano(app, android)
        app.viagem.iniciar()
        fundo.sincronizar()
        app.viagem.pausar()
        fundo.sincronizar()
        self.assertNotIn("parar", android.nomes())
        self.assertTrue(textos(app)[0].startswith("Viagem pausada"))

    def test_minimizar_gravando_liga_mesmo_sem_aviso_da_tela(self):
        app, android = self._app(), AndroidFalso()
        fundo = SegundoPlano(app, android)
        app.viagem.iniciar()
        fundo.ao_pausar()
        self.assertTrue(fundo.minimizado)
        self.assertIn("iniciar", android.nomes())
        fundo.ao_voltar()


class TesteLugaresNoMapa(unittest.TestCase):
    def test_quadrado_do_centro_tem_lugares_do_mais_confiavel_ao_menos(self):
        cx, cy = int(-16.68 // busca.CELULA_MAPA), int(-49.26 // busca.CELULA_MAPA)
        lugares = busca.lugares_da_celula(cx, cy)
        self.assertGreater(len(lugares), 50)
        self.assertLessEqual(len(lugares), busca.MAX_POR_CELULA)
        confs = [l[4] for l in lugares]
        self.assertEqual(confs, sorted(confs, reverse=True))
        self.assertGreaterEqual(confs[-1], busca.CONF_MAPA_MIN)
        for _, _, lat, lon, _ in lugares:
            self.assertTrue(cx * busca.CELULA_MAPA <= lat < (cx + 1) * busca.CELULA_MAPA)
            self.assertTrue(cy * busca.CELULA_MAPA <= lon < (cy + 1) * busca.CELULA_MAPA)

    def test_grupo_da_categoria(self):
        self.assertEqual(busca.grupo_da_categoria("padaria"), "comida")
        self.assertEqual(busca.grupo_da_categoria("farmácia"), "saude")
        self.assertEqual(busca.grupo_da_categoria("móveis"), "compras")
        self.assertEqual(busca.grupo_da_categoria(""), "outros")


if __name__ == "__main__":
    unittest.main()
