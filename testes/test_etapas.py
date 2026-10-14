"""Etapas arriscadas (diagnostico.etapa): se o app cai no meio de uma, a próxima abertura sabe qual foi."""
import os
import shutil
import sys
import tempfile
import unittest

import caminhos  # noqa: F401
import diagnostico


class TesteEtapas(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.saida, self.erro, self.gancho = sys.stdout, sys.stderr, sys.excepthook

    def tearDown(self):
        sys.stdout, sys.stderr, sys.excepthook = self.saida, self.erro, self.gancho
        diagnostico._caminho = diagnostico._pasta = None
        shutil.rmtree(self.pasta, ignore_errors=True)

    def abrir(self):
        diagnostico.iniciar(self.pasta, "teste")
        sys.stdout, sys.stderr = self.saida, self.erro

    def test_etapa_que_terminou_nao_conta(self):
        self.abrir()
        diagnostico.etapa("umbra_rosto")
        diagnostico.etapa_ok("umbra_rosto")
        self.abrir()
        self.assertIsNone(diagnostico.etapa_que_derrubou())

    def test_etapa_interrompida_e_lembrada_uma_vez(self):
        self.abrir()
        diagnostico.etapa("umbra_escuta")             # e o app "cai" aqui
        self.abrir()
        self.assertEqual(diagnostico.etapa_que_derrubou(), "umbra_escuta")
        self.assertTrue(diagnostico.fechou_com_erro())
        with open(os.path.join(self.pasta, "diagnostico.txt"), encoding="utf-8") as f:
            self.assertIn("fechou de repente durante: umbra_escuta", f.read())
        self.abrir()                                  # na abertura seguinte já não conta de novo
        self.assertIsNone(diagnostico.etapa_que_derrubou())

    def test_ok_de_outra_etapa_nao_apaga(self):
        self.abrir()
        diagnostico.etapa("umbra_escuta")
        diagnostico.etapa_ok("umbra_rosto")
        self.abrir()
        self.assertEqual(diagnostico.etapa_que_derrubou(), "umbra_escuta")

    def test_erro_do_java_entra_no_registro(self):
        self.abrir()
        with open(os.path.join(self.pasta, "erro_java.txt"), "w", encoding="utf-8") as f:
            f.write("java.lang.NullPointerException: teste")
        self.abrir()
        with open(os.path.join(self.pasta, "diagnostico.txt"), encoding="utf-8") as f:
            self.assertIn("NullPointerException: teste", f.read())
        self.assertFalse(os.path.exists(os.path.join(self.pasta, "erro_java.txt")))

    def test_envia_so_as_ultimas_aberturas(self):
        for _ in range(diagnostico.SESSOES_A_ENVIAR + 5):
            self.abrir()
        texto = diagnostico.texto_para_enviar()
        self.assertEqual(texto.count(diagnostico.INICIO), diagnostico.SESSOES_A_ENVIAR)


if __name__ == "__main__":
    unittest.main()
