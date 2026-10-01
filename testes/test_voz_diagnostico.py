import os
import sys
import tempfile
import time
import unittest

from kivy.clock import Clock

import diagnostico
import voz


class FalaTravada:
    """Motor de voz de mentira que nunca avisa que terminou de falar."""
    estado = 1
    ocupada = False
    nomesVozes = ""
    vozGrave = -2
    faladas = []
    paradas = 0

    @classmethod
    def falar(cls, texto):
        cls.faladas.append(texto)
        cls.ocupada = True
        return True

    @classmethod
    def parar(cls):
        cls.paradas += 1
        cls.ocupada = False

    @classmethod
    def escolherVoz(cls, i):
        pass

    @classmethod
    def ajustar(cls, *a):
        pass


class TesteVoz(unittest.TestCase):
    def test_fala_travada_e_cortada_e_a_fila_anda(self):
        antigos = voz.TRAVADA_BASE_S, voz.TRAVADA_POR_LETRA_S
        voz.TRAVADA_BASE_S, voz.TRAVADA_POR_LETRA_S = 0.3, 0.0
        try:
            v = voz.Voz(tempfile.mkdtemp())
            v._fala = FalaTravada
            v.falar(["recalculando"], 2)
            v.falar(["gps_ok"], 0)
            fim = time.time() + 5
            while time.time() < fim and len(FalaTravada.faladas) < 2:
                Clock.tick()
                time.sleep(0.02)
            self.assertEqual(FalaTravada.faladas, ["Recalculando a rota.", "Sinal do GPS de volta."])
            self.assertGreaterEqual(FalaTravada.paradas, 1)
        finally:
            voz.TRAVADA_BASE_S, voz.TRAVADA_POR_LETRA_S = antigos


class TesteDiagnostico(unittest.TestCase):
    def setUp(self):
        self.stdout, self.stderr, self.hook = sys.stdout, sys.stderr, sys.excepthook

    def tearDown(self):
        sys.stdout, sys.stderr, sys.excepthook = self.stdout, self.stderr, self.hook

    def test_registra_prints_e_erros_e_avisa_na_proxima(self):
        pasta = tempfile.mkdtemp()
        diagnostico.iniciar(pasta, "teste")
        self.assertFalse(diagnostico.fechou_com_erro())
        print("[teste] uma linha")
        try:
            raise ValueError("erro de teste")
        except ValueError:
            diagnostico.registrar_erro(*sys.exc_info(), onde="erro que fechou o app")
        texto = diagnostico.texto_para_enviar()
        self.assertIn("[teste] uma linha", texto)
        self.assertIn("ValueError: erro de teste", texto)
        sys.stdout, sys.stderr = self.stdout, self.stderr
        diagnostico.iniciar(pasta, "teste")   # "abriu de novo"
        self.assertTrue(diagnostico.fechou_com_erro())
        sys.stdout, sys.stderr = self.stdout, self.stderr
        diagnostico.iniciar(pasta, "teste")   # a sessão anterior não teve erro
        self.assertFalse(diagnostico.fechou_com_erro())
        self.assertTrue(os.path.getsize(os.path.join(pasta, "diagnostico.txt")) < diagnostico.MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
