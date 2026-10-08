"""A organização em pastas: cada arquivo de código é achado pelo nome de antes."""
import importlib
import os
import unittest

import caminhos


class TesteOrganizacao(unittest.TestCase):
    def _modulos(self):
        for pasta in caminhos.PASTAS:
            for nome in sorted(os.listdir(os.path.join(caminhos.RAIZ, pasta))):
                if nome.endswith(".py"):
                    yield pasta, nome[:-3]

    def test_as_pastas_existem_e_nenhum_nome_se_repete(self):
        vistos = {}
        for pasta, modulo in self._modulos():
            self.assertNotIn(modulo, vistos, "%s está em %s e em %s" % (modulo, vistos.get(modulo), pasta))
            vistos[modulo] = pasta
        self.assertGreater(len(vistos), 30)
        soltos = [n for n in os.listdir(caminhos.RAIZ) if n.endswith(".py")]
        self.assertEqual(sorted(soltos), ["caminhos.py", "hooks.py", "main.py"])     # o resto está nas pastas

    def test_cada_modulo_vem_da_pasta_dele(self):
        for pasta, modulo in self._modulos():
            if modulo == "gps_android":
                continue                                    # só existe no Android (precisa do jnius)
            m = importlib.import_module(modulo)
            arquivo = os.path.normcase(os.path.abspath(m.__file__))
            esperado = os.path.normcase(os.path.join(caminhos.RAIZ, pasta, modulo + ".py"))
            self.assertEqual(arquivo, esperado)

    def test_voz_e_sons_sao_o_codigo_e_acham_as_gravacoes(self):
        # (audio/voz.py e a pasta audio/voz/ têm o mesmo nome: o Python tem de escolher o arquivo)
        import sons
        import voz
        self.assertTrue(voz.__file__.endswith("voz.py") and sons.__file__.endswith("sons.py"))
        self.assertTrue(os.path.exists(os.path.join(voz.PASTA_VOZ, "chegou.wav")))
        self.assertTrue(os.path.exists(os.path.join(sons.PASTA, "curva.wav")))

    def test_dados_e_chaves_ficam_na_raiz_do_projeto(self):
        import busca
        import chaves
        import mapa_vetor
        import sinais
        for caminho in (busca.BASE, mapa_vetor.PACOTE, sinais.ARQUIVO):
            self.assertTrue(os.path.exists(caminho), caminho)
            self.assertEqual(os.path.normcase(os.path.dirname(os.path.dirname(caminho))), os.path.normcase(caminhos.RAIZ))
        self.assertEqual(os.path.normcase(os.path.dirname(chaves._ARQUIVO)), os.path.normcase(caminhos.RAIZ))
        self.assertEqual(os.path.normcase(os.path.dirname(mapa_vetor.PRONTOS)),
                         os.path.normcase(os.path.join(caminhos.RAIZ, "dados")))


if __name__ == "__main__":
    unittest.main()
