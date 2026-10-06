"""Ajustes gravados com segurança e a busca só no celular (enquanto digita)."""
import json
import os
import tempfile
import threading
import unittest

import busca
import rede
from ajustes import Ajustes


class TesteAjustes(unittest.TestCase):
    def test_grava_inteiro_e_sem_sobra(self):
        with tempfile.TemporaryDirectory() as pasta:
            a = Ajustes(pasta)
            a["firebase"] = "https://x.firebaseio.com"
            self.assertEqual(sorted(os.listdir(pasta)), ["ajustes.json"])      # sem .tmp sobrando
            self.assertEqual(Ajustes(pasta)["firebase"], "https://x.firebaseio.com")

    def test_arquivo_estragado_volta_ao_padrao_sem_quebrar(self):
        with tempfile.TemporaryDirectory() as pasta:
            with open(os.path.join(pasta, "ajustes.json"), "w") as f:
                f.write('{"limite_kmh": 4')                                      # cortado no meio
            a = Ajustes(pasta)
            self.assertEqual(a["limite_kmh"], 32)
            a["limite_kmh"] = 40
            self.assertEqual(Ajustes(pasta)["limite_kmh"], 40)

    def test_duas_threads_gravando(self):
        with tempfile.TemporaryDirectory() as pasta:
            a = Ajustes(pasta)

            def gravar(chave):
                for k in range(60):
                    a[chave] = k
            ts = [threading.Thread(target=gravar, args=(c,)) for c in ("ritmo", "alfa")]
            [t.start() for t in ts]
            [t.join() for t in ts]
            with open(os.path.join(pasta, "ajustes.json")) as f:
                dados = json.load(f)                                             # JSON inteiro
            self.assertEqual((dados["ritmo"], dados["alfa"]), (59, 59))

    def test_atalhos_comecam_vazios(self):
        with tempfile.TemporaryDirectory() as pasta:
            self.assertEqual(Ajustes(pasta)["atalhos"], {})


class TesteBuscaLocal(unittest.TestCase):
    def test_enquanto_digita_nao_vai_a_internet(self):
        real = rede.baixar_json
        rede.baixar_json = lambda *a, **k: self.fail("a busca local não pode usar a internet")
        try:
            salvos = [{"nome": "Farmácia da esquina", "endereco": "", "lat": -16.68, "lon": -49.25}]
            achados = busca.buscar_local("farmac", (-16.68, -49.25), salvos)
        finally:
            rede.baixar_json = real
        self.assertGreater(len(achados), 5)
        self.assertEqual(achados[0]["nome"], "Farmácia da esquina")             # o salvo vem primeiro
        self.assertTrue(all(l["dist_m"] is not None for l in achados))

    def test_busca_completa_continua_igual(self):
        achados = busca.buscar("bosque dos buritis")
        self.assertIn("Buritis", achados[0]["nome"])


if __name__ == "__main__":
    unittest.main()
