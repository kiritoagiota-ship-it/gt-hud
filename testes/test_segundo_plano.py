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

    def __getattr__(self, nome):
        def registrar(*args):
            self.chamadas.append((nome,) + args)
        return registrar

    def bolha_permitida(self):
        return self.permitida

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

    def test_bolha_sem_permissao_nao_aparece_mas_navega(self):
        app, android = AppFalso(), AndroidFalso(permitida=False)
        fundo = SegundoPlano(app, android)
        fundo.ao_pausar()
        self.assertNotIn("mostrar_bolha", android.nomes())
        app.gps.leituras.append({"lat": -16.68, "lon": -49.25})
        self.assertTrue(esperar(lambda: len(app.processadas) == 1))
        fundo.ao_voltar()


if __name__ == "__main__":
    unittest.main()
