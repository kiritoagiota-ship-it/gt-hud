import threading
import time
import unittest

import rede
import segundo_plano
from segundo_plano import SegundoPlano, textos


class AndroidFalso:
    def __init__(self, permitida=True):
        self.chamadas = []
        self.bolha = object()
        self.permitida = permitida
        self.painel_abre = True    # None = sem a classe do painel; False = o Android recusou

    def __getattr__(self, nome):
        def registrar(*args):
            self.chamadas.append((nome,) + args)
        return registrar

    def bolha_permitida(self):
        return self.permitida

    def mostrar_painel(self, dados, claro):
        self.chamadas.append(("mostrar_painel", dados, claro))
        return self.painel_abre is not None

    def estado_painel(self):
        return (1, "") if self.painel_abre else (-1, "o Android recusou")

    def nomes(self):
        return [c[0] for c in self.chamadas]


class GpsFalso:
    def __init__(self):
        self.leituras = []

    def ler_direto(self):
        return self.leituras.pop(0) if self.leituras else None


class NavFalsa:
    chegou = False


class AppFalso:
    def __init__(self):
        self.nav = NavFalsa()
        self.estado_nav = {"restante_s": 480, "restante_m": 2300, "manobra": {"acao": "direita",
                           "ruas": "Rua 5"}, "dist_manobra": 200, "fora_da_rota": False}
        self.recalculando = False
        self.ajustes = {"segundo_plano": True, "bolha": True}
        self.gps = GpsFalso()
        self.processadas, self.threads = [], set()
        self.bombeadas = 0

        class Voz:
            def bombear(s):
                self.bombeadas += 1
        self.voz = Voz()

    def processar_leitura(self, d):
        self.processadas.append(d)
        self.threads.add(threading.current_thread().name)

    def vigiar_gps(self):
        pass

    def conferir_fim(self):
        pass


def esperar(condicao, segundos=3.0):
    fim = time.time() + segundos
    while time.time() < fim and not condicao():
        time.sleep(0.02)
    return condicao()


class TesteSegundoPlano(unittest.TestCase):
    def setUp(self):
        self.intervalo = segundo_plano.INTERVALO_S
        segundo_plano.INTERVALO_S = 0.02

    def tearDown(self):
        segundo_plano.INTERVALO_S = self.intervalo
        rede.desviar_respostas(None)

    def test_textos_da_notificacao_e_da_bolha(self):
        titulo, texto, l1, l2 = textos(AppFalso())
        self.assertTrue(titulo.startswith("8 min  ·  2,3 km  ·  chega às "))
        self.assertEqual(texto, "Vire à direita em 200 m (Rua 5)")
        self.assertEqual((l1, l2), ("8 min", "2,3 km"))

    def test_minimizado_continua_navegando_e_para_ao_voltar(self):
        app, android = AppFalso(), AndroidFalso()
        fundo = SegundoPlano(app, android)
        fundo.comecou()
        fundo.ao_pausar()
        self.assertTrue(fundo.minimizado)
        self.assertIn("mostrar_bolha", android.nomes())
        app.gps.leituras += [{"lat": -16.68, "lon": -49.25, "speed": 5, "accuracy": 5}] * 3
        self.assertTrue(esperar(lambda: len(app.processadas) == 3))
        self.assertEqual(app.threads, {"segundo-plano"})       # fora da thread do Kivy
        self.assertGreater(app.bombeadas, 0)                     # a voz andou sem o Clock
        # resposta da internet (ex.: rota recalculada) com o app minimizado
        recebido = []
        rede._entregar(lambda v: recebido.append((v, threading.current_thread().name)), "rota nova")
        self.assertTrue(esperar(lambda: recebido))
        self.assertEqual(recebido[0], ("rota nova", "segundo-plano"))
        fundo.ao_voltar()
        self.assertFalse(fundo.minimizado)
        self.assertIn("esconder_bolha", android.nomes())
        self.assertIsNone(rede._desvio)
        app.gps.leituras.append({"lat": 0, "lon": 0})
        time.sleep(0.15)
        self.assertEqual(len(app.processadas), 3)              # parou de verdade
        fundo.terminou()
        self.assertIn("parar", android.nomes())

    def test_sem_rota_ou_desligado_nao_faz_nada(self):
        app, android = AppFalso(), AndroidFalso()
        app.nav = None
        SegundoPlano(app, android).ao_pausar()
        self.assertEqual(android.chamadas, [])
        app = AppFalso()
        app.ajustes["segundo_plano"] = False
        fundo = SegundoPlano(app, android)
        fundo.comecou()
        fundo.ao_pausar()
        self.assertFalse(fundo.minimizado)
        self.assertEqual(android.chamadas, [])

    def test_so_contando_a_bateria_segue_no_bolso_sem_janela(self):
        """Sem rota, com uma carga da moto sendo contada: minimizar mantém o GPS (o dono
        abre o app, minimiza e põe no bolso), só com a notificação."""
        class Bateria:
            ativa, metros, barras = True, 12400.0, 4
        app, android = AppFalso(), AndroidFalso()
        app.nav, app.bateria = None, Bateria()
        self.assertEqual(textos(app)[0], "Contando os km da carga  ·  12,4 km")
        fundo = SegundoPlano(app, android)
        fundo.ao_pausar()                                        # serviço ainda desligado: o Android não
        self.assertFalse(fundo.minimizado)                       # deixa ligar com o app saindo da tela
        self.assertNotIn("iniciar", android.nomes())             # (a 1.0.67 ligava aqui e o app caía)
        fundo.sincronizar()                                      # com o app aberto: liga
        self.assertIn("iniciar", android.nomes())
        fundo.ao_pausar()
        self.assertTrue(fundo.minimizado)
        self.assertNotIn("mostrar_bolha", android.nomes())
        self.assertNotIn("mostrar_painel", android.nomes())
        app.gps.leituras.append({"lat": -16.68, "lon": -49.25, "speed": 10.0})
        self.assertTrue(esperar(lambda: app.processadas))        # a leitura chegou com o app minimizado
        fundo.ao_voltar()
        Bateria.ativa = False                                    # nunca marcou carga: como antes, nada
        android2 = AndroidFalso()
        SegundoPlano(app, android2).ao_pausar()
        self.assertEqual(android2.chamadas, [])

    def test_bolha_sem_permissao_nao_aparece_mas_navega(self):
        app, android = AppFalso(), AndroidFalso(permitida=False)
        fundo = SegundoPlano(app, android)
        fundo.ao_pausar()
        self.assertNotIn("mostrar_bolha", android.nomes())
        app.gps.leituras.append({"lat": -16.68, "lon": -49.25})
        self.assertTrue(esperar(lambda: len(app.processadas) == 1))
        fundo.ao_voltar()



class TestePainelFlutuante(unittest.TestCase):
    """Minimizado numa rota: retângulo com o caminho à frente, a curva e a velocidade."""

    def _nav(self, curva=False):
        from navegacao import Navegacao
        from testes.apoio import Fala, rota_reta
        import rota as rotas
        if curva:   # 200 m para o norte e depois para o leste
            pts = [(-16.68 + d / 111320.0, -49.25) for d in range(0, 201, 10)]
            lat = pts[-1][0]
            pts += [(lat, -49.25 + d / (111320.0 * 0.958)) for d in range(10, 301, 10)]
            r = rotas.Rota(pts, [], [800.0] * 20, 120, "Teste")
        else:
            r = rota_reta(600)
        nav = Navegacao(r, Fala())
        nav.atualizar(r.pontos[10][0], r.pontos[10][1], 25.0, 1.0)     # 100 m depois do começo
        return nav

    def _pontos(self, nav):
        texto, inicio, aqui = segundo_plano.desenho_da_rota(nav)
        return [tuple(map(float, p.split(","))) for p in texto.split(";")], inicio, aqui

    def test_desenho_reto_em_metros_com_inicio_e_posicao(self):
        pontos, inicio, aqui = self._pontos(self._nav())
        self.assertAlmostEqual(aqui, 100, delta=2)                      # a pessoa está 100 m depois do começo
        self.assertIn(inicio, (20.0, 30.0))                             # uns 70 m para trás, em distância "redonda"
        self.assertEqual(pontos[0], (0.0, 0.0))                         # medidos a partir do primeiro ponto
        self.assertTrue(all(abs(x) < 0.5 for x, _ in pontos))           # rota para o norte: só o y cresce
        passos = [round(b[1] - a[1]) for a, b in zip(pontos, pontos[1:])]
        self.assertTrue(all(p == 10 for p in passos[:-1]), passos)      # um ponto a cada 10 m
        self.assertAlmostEqual(inicio + pontos[-1][1], 520, delta=3)    # 420 m à frente da pessoa

    def test_mesmos_pontos_de_um_envio_para_o_outro(self):
        nav = self._nav()
        a, inicio_a, _ = self._pontos(nav)
        nav.atualizar(nav.rota.pontos[11][0], nav.rota.pontos[11][1], 25.0, 2.2)   # andou só 10 m
        b, inicio_b, _ = self._pontos(nav)
        # os pontos são tirados das mesmas distâncias da rota: o desenho não treme
        em_a = {round(inicio_a + y) for _, y in a}
        em_b = {round(inicio_b + y) for _, y in b}
        self.assertGreaterEqual(len(em_a & em_b), len(a) - 4)

    def test_curva_a_direita_vai_para_o_leste(self):
        pontos, inicio, aqui = self._pontos(self._nav(curva=True))
        x_fim, y_fim = pontos[-1]
        self.assertGreater(x_fim, 250)                                  # depois da curva, o caminho segue para o leste
        self.assertAlmostEqual(inicio + y_fim, 200, delta=6)            # a curva fica a 200 m do começo da rota

    def test_minimizado_mostra_o_painel_e_nao_a_bolha(self):
        app, android = AppFalso(), AndroidFalso()
        app.ajustes["flutuante_tipo"] = "painel"
        app.nav = self._nav()
        app.estado_nav = {"restante_s": 480, "restante_m": 2300, "dist_manobra": 200, "fora_da_rota": False,
                          "manobra": {"acao": "direita", "ruas": "Rua 5"}, "alerta": None}

        class Filtro:
            def previsto(self):
                return 31.6
        app.filtro = Filtro()
        fundo = SegundoPlano(app, android)
        fundo.ao_pausar()
        chamadas = dict((c[0], c[1:]) for c in android.chamadas)
        self.assertIn("mostrar_painel", chamadas)
        self.assertNotIn("mostrar_bolha", chamadas)
        distancia, instrucao, rua, vel, resto, desenho, alerta, inicio, aqui, vel_ms = chamadas["mostrar_painel"][0]
        self.assertEqual((distancia, instrucao, rua, vel, alerta), ("200 m", "Vire à direita", "Rua 5", "32", 0))
        self.assertAlmostEqual(aqui, 100, delta=2)
        self.assertAlmostEqual(vel_ms, 25 / 3.6, places=2)              # para o desenho andar entre as posições
        self.assertTrue(resto.startswith("8 min · 2,3 km · "))
        self.assertGreater(len(desenho.split(";")), 10)
        fundo.ao_voltar()
        self.assertIn("esconder_painel", android.nomes())

    def test_painel_que_nao_abre_cai_para_a_bolha(self):
        for abre in (None, False):      # sem a classe do painel / o Android recusou abrir
            app, android = AppFalso(), AndroidFalso()
            android.painel_abre = abre
            app.ajustes["flutuante_tipo"] = "painel"
            app.nav = self._nav()
            app.estado_nav = {"restante_s": 480, "restante_m": 2300, "dist_manobra": 200, "fora_da_rota": False,
                              "manobra": {"acao": "direita", "ruas": "Rua 5"}, "alerta": None}
            fundo = SegundoPlano(app, android)
            fundo.ao_pausar()
            if abre is False:           # só descobre depois de pedir: confere 1,5 s depois
                fundo._conferir_painel_em = 0.0
                fundo.atualizar_painel()
            self.assertIn("mostrar_bolha", android.nomes(), abre)
            self.assertFalse(fundo._painel_a_vista)
            fundo.ao_voltar()

    def test_avenida_e_fora_da_rota_mudam_a_cor(self):
        app = AppFalso()
        app.nav = self._nav()
        app.estado_nav = {"restante_s": 60, "restante_m": 300, "dist_manobra": 50, "fora_da_rota": False,
                          "manobra": None, "alerta": {"tipo": "avenida", "em_m": 0, "nivel": 3}}
        self.assertEqual(segundo_plano.dados_do_painel(app)[6], 2)
        app.estado_nav["alerta"]["em_m"] = 120                          # avenida ainda à frente: normal
        self.assertEqual(segundo_plano.dados_do_painel(app)[6], 0)
        app.estado_nav["fora_da_rota"] = True
        self.assertEqual(segundo_plano.dados_do_painel(app)[:2], ("Fora da rota", "Volte para a rota"))


if __name__ == "__main__":
    unittest.main()
