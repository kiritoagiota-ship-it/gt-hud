"""Corrida ao vivo: o app manda posição, rota e caminho; no fim, some tudo."""
import json
import time
import unittest
import urllib.error

import ao_vivo
import rede
import rota as rotas
from ferramentas.firebase_falso import servidor
from testes.apoio import rota_reta


def esperar(condicao, segundos=4.0):
    fim = time.time() + segundos
    while time.time() < fim and not condicao():
        time.sleep(0.02)
    return condicao()


class TesteEndereco(unittest.TestCase):
    def test_aceita_so_endereco_de_realtime_database(self):
        ok = "https://gt-hud-1234-default-rtdb.firebaseio.com"
        self.assertEqual(ao_vivo.limpar_endereco(" " + ok + "/ "), ok)
        self.assertEqual(ao_vivo.limpar_endereco("gt-hud-1234-default-rtdb.firebaseio.com"), ok)
        self.assertEqual(ao_vivo.limpar_endereco("https://x-default-rtdb.europe-west1.firebasedatabase.app/"),
                         "https://x-default-rtdb.europe-west1.firebasedatabase.app")
        for ruim in ("", "abc", "https://google.com", "http://x.firebaseio.com", "https://firebaseio.com.evil.com",
                     "https://console.firebase.google.com/project/x"):
            self.assertIsNone(ao_vivo.limpar_endereco(ruim), ruim)

    def test_link_leva_banco_e_codigo_depois_do_jogo_da_velha(self):
        self.assertEqual(ao_vivo.link("https://x.firebaseio.com", "abc"), ao_vivo.PAGINA + "#x.firebaseio.com/abc")


class TesteAoVivo(unittest.TestCase):
    def setUp(self):
        self.http, self.banco, self.base = servidor()
        self._intervalos = ao_vivo.ENVIAR_A_CADA_S, ao_vivo.PARADO_A_CADA_S
        ao_vivo.ENVIAR_A_CADA_S = 0.0

    def tearDown(self):
        ao_vivo.ENVIAR_A_CADA_S, ao_vivo.PARADO_A_CADA_S = self._intervalos
        self.http.shutdown()
        self.http.server_close()

    def _pub(self, corrida):
        return rede.baixar_json("%s/corridas/%s/pub.json" % (self.base, corrida.codigo))

    def test_corrida_inteira(self):
        rota = rota_reta(600)
        corrida = ao_vivo.AoVivo(self.base)
        link = corrida.comecar(rota, "Barbearia Imagem")
        self.assertTrue(link.endswith("/" + corrida.codigo))
        self.assertTrue(esperar(lambda: corrida.enviados >= 1))
        pub = self._pub(corrida)
        self.assertEqual(pub["destino"], "Barbearia Imagem")
        linha = rotas.decodificar_polyline(pub["rota"]["linha"], 1e5)
        self.assertEqual(len(linha), len(rota.pontos))
        self.assertAlmostEqual(pub["rota"]["dlat"], rota.pontos[-1][0], places=5)

        for k in range(1, 6):   # anda 100 m, 5 leituras
            lat, lon = rota.pontos[k * 2]
            n = corrida.enviados
            corrida.leitura(lat, lon, 25.4, 0, 600 - k * 20, 120 - k * 4)
            self.assertTrue(esperar(lambda: corrida.enviados > n))
        pub = self._pub(corrida)
        self.assertEqual((pub["pos"]["v"], pub["pos"]["fm"], pub["pos"]["e"]), (25, 500, "indo"))
        self.assertAlmostEqual(pub["pos"]["lat"], rota.pontos[10][0], places=5)
        feito = [p for k in sorted(pub["tr"]) for p in rotas.decodificar_polyline(pub["tr"][k], 1e5)]
        self.assertEqual(len(feito), 5)
        self.assertEqual(pub["pos"]["n"], len(pub["tr"]))
        # a página pede só os pedaços que faltam
        novos = rede.baixar_json('%s/corridas/%s/pub/tr.json?orderBy="$key"&startAt="00003"' % (
            self.base, corrida.codigo))
        self.assertEqual(sorted(novos), ["00003", "00004"])

        nova = rota_reta(300)
        corrida.trocar_rota(nova)
        self.assertTrue(esperar(lambda: (self._pub(corrida).get("rota") or {}).get("rv") == 2))

        corrida.terminar(chegou=True)
        corrida.esperar_fim()
        self.assertTrue(corrida.fim_avisado)
        pub = self._pub(corrida)
        self.assertEqual(pub["pos"]["e"], "chegou")
        self.assertNotIn("tr", pub)           # o caminho e a posição somem
        self.assertNotIn("lat", pub["pos"])
        self.assertNotIn("rota", pub)

    def test_ninguem_le_a_senha_nem_lista_nem_escreve_sem_ela(self):
        corrida = ao_vivo.AoVivo(self.base)
        corrida.comecar(rota_reta(100), "X")
        self.assertTrue(esperar(lambda: corrida.enviados >= 1))
        for caminho in ("corridas/%s/s" % corrida.codigo, "corridas/%s" % corrida.codigo, "corridas"):
            with self.assertRaises(urllib.error.HTTPError):
                rede.baixar_json("%s/%s.json" % (self.base, caminho))
        with self.assertRaises(urllib.error.HTTPError):   # outra pessoa tentando mexer na corrida
            rede.enviar("%s/corridas/%s.json" % (self.base, corrida.codigo), {"s": "outra", "pub/pos": {}}, "PATCH")
        self.assertNotIn(corrida.senha, json.dumps(self._pub(corrida)))
        corrida.terminar()
        corrida.esperar_fim()

    def test_sem_internet_o_caminho_nao_se_perde(self):
        rota = rota_reta(600)
        corrida = ao_vivo.AoVivo(self.base)
        corrida.comecar(rota, "X")
        self.assertTrue(esperar(lambda: corrida.enviados >= 1))
        real = ao_vivo._Linha.enviar

        def caiu(*a, **k):
            raise OSError("sem internet")
        ao_vivo._Linha.enviar = caiu
        try:
            for k in (2, 4, 6):
                corrida.leitura(rota.pontos[k][0], rota.pontos[k][1], 20, 0, 500, 100)
                time.sleep(0.08)
            self.assertTrue(esperar(lambda: corrida.ultimo_erro is not None))
        finally:
            ao_vivo._Linha.enviar = real
        n = corrida.enviados
        corrida.leitura(rota.pontos[8][0], rota.pontos[8][1], 20, 0, 400, 80)
        self.assertTrue(esperar(lambda: corrida.enviados > n))
        pub = self._pub(corrida)
        feito = [p for k in sorted(pub["tr"]) for p in rotas.decodificar_polyline(pub["tr"][k], 1e5)]
        self.assertEqual(len(feito), 4)
        corrida.terminar()
        corrida.esperar_fim()

    def test_conexao_cai_e_o_envio_seguinte_abre_outra(self):
        rota = rota_reta(600)
        corrida = ao_vivo.AoVivo(self.base)
        corrida.comecar(rota, "X")
        self.assertTrue(esperar(lambda: corrida.enviados >= 1))
        corrida._linha._con.close()          # o servidor fechou a conexão parada
        n = corrida.enviados
        corrida.leitura(rota.pontos[5][0], rota.pontos[5][1], 20, 0, 400, 80)
        self.assertTrue(esperar(lambda: corrida.enviados > n))
        self.assertIsNone(corrida.ultimo_erro)
        corrida.terminar()
        corrida.esperar_fim()
        self.assertTrue(corrida.fim_avisado)

    def test_testar_banco(self):
        self.assertIsNone(ao_vivo.testar(self.base))
        self.assertIn("internet", ao_vivo.testar("http://127.0.0.1:9"))

    def test_encerrar_esquecida(self):
        corrida = ao_vivo.AoVivo(self.base)
        corrida.comecar(rota_reta(100), "X")
        self.assertTrue(esperar(lambda: corrida.enviados >= 1))
        corrida.leitura(-16.68, -49.25, 10, 0, 50, 10)
        self.assertTrue(esperar(lambda: "pos" in self._pub(corrida)))
        corrida.ativo = False   # o app "morreu" sem avisar o fim
        ao_vivo.encerrar_esquecida(self.base, corrida.codigo, corrida.senha)
        pub = self._pub(corrida)
        self.assertEqual(pub["pos"]["e"], "encerrou")
        self.assertEqual(sorted(pub), ["fim", "pos"])     # posição, rota e caminho apagados


if __name__ == "__main__":
    unittest.main()
