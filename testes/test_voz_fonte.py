"""Qual voz fala: a gravada do app (padrão) ou a do celular.

Até a 1.0.58 o app sempre usava a voz do celular quando ela existia: o dono
regravou a voz (ElevenLabs) e "não saiu a voz nova". Estes testes travam a escolha.
"""
import tempfile
import unittest

import voz


class _Motor:
    """A classe Java Fala de mentira: o celular TEM voz em português."""
    estado = 1
    ocupada = False

    def __init__(self):
        self.ditas = []

    def falar(self, frase):
        self.ditas.append(frase)
        return True

    def parar(self):
        pass

    def escolherVoz(self, i):
        pass

    def ajustar(self, *a):
        pass


class TesteFonteDaVoz(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.v = voz.Voz(self.pasta.name)
        self.v._fala = self.motor = _Motor()
        self.v._agendar = lambda espera: None
        self.gravadas = []
        self.v._tocar_gravada = lambda pedacos, agora: self.gravadas.append(list(pedacos))

    def tearDown(self):
        self.pasta.cleanup()

    def test_o_padrao_e_a_voz_gravada_mesmo_com_voz_no_celular(self):
        self.assertTrue(self.v.gravada)
        self.v.falar(["senhor", "em_200", "vire_direita"])
        self.assertEqual(self.gravadas, [["senhor", "em_200", "vire_direita"]])
        self.assertEqual(self.motor.ditas, [])

    def test_frase_com_detalhe_sai_na_versao_gravada(self):
        self.v.falar(["avenida"], 1, "Atenção: Rua 82 à frente, de trânsito pesado, por 500 metros.")
        self.assertEqual((self.gravadas, self.motor.ditas), ([["avenida"]], []))

    def test_voz_do_celular_quando_escolhida(self):
        self.v.gravada = False
        self.v.falar(["avenida"], 1, "Atenção: Rua 82 à frente, de trânsito pesado, por 500 metros.")
        self.assertEqual(self.gravadas, [])
        self.assertEqual(self.motor.ditas, ["Atenção: Rua 82 à frente, de trânsito pesado, por 500 metros."])

    def test_sem_gravacao_para_a_frase_o_celular_fala_em_vez_de_ficar_mudo(self):
        self.v.falar([], 1, "Um aviso que não tem gravação.")
        self.assertEqual((self.gravadas, self.motor.ditas), ([], ["Um aviso que não tem gravação."]))

    def test_sem_voz_no_celular_a_gravada_fala_sempre(self):
        self.v._fala = None
        self.v.gravada = False
        self.v.falar(["recalculando"])
        self.assertEqual(self.gravadas, [["recalculando"]])

    def test_o_teste_da_voz_gravada_usa_uma_frase_em_pedacos(self):
        self.v.testar()
        self.assertEqual(self.gravadas, [["senhor", "em_200", "vire_direita"]])


if __name__ == "__main__":
    unittest.main()
