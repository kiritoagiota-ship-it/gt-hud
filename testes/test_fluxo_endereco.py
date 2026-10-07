"""Ruas coloridas pela velocidade (fluxo.py) e endereço de um ponto (busca.endereco_de)."""
import json
import unittest
import urllib.error

import busca
import fluxo
import rede


class TesteFluxo(unittest.TestCase):
    def test_niveis(self):
        self.assertEqual([fluxo.nivel_de(f) for f in (1.0, 0.8, 0.74, 0.5, 0.2, 0.0)], [0, 0, 1, 2, 3, 3])
        self.assertEqual(fluxo.nivel_de(0.9, fechada=True), 4)

    def test_pedacos_da_vista_ficam_em_goiania(self):
        centro = fluxo.tiles_da_caixa(-16.70, -49.28, -16.66, -49.24)
        self.assertEqual(len(centro), 1)
        self.assertEqual(len(fluxo.tiles_da_caixa(-17.5, -50.5, -15.5, -48.5)), 25)     # Goiânia inteira, não o estado
        self.assertEqual(fluxo.tiles_da_caixa(-10.0, -40.0, -9.0, -39.0), [])           # fora da cidade

    def test_segmentos_viram_lat_lon_dentro_do_pedaco(self):
        x, y = fluxo.tile_de(-16.68, -49.25)
        camada = (4096, [
            (2, {"traffic_level": 0.2}, [[0, 0, 2048, 2048, 4096, 4096]]),
            (2, {"traffic_level": 0.9, "road_closure": True}, [[100, 100, 200, 200]]),
            (1, {"traffic_level": 0.1}, [[5, 5]]),                 # ponto: não é rua
            (2, {"traffic_level": 0.6}, [[7, 7]])])                # um ponto só: sem linha
        segmentos = fluxo.segmentos_da_camada(camada, x, y)
        self.assertEqual([n for _, n in segmentos], [3, 4])
        pontos = segmentos[0][0]
        meio = pontos[1]
        self.assertEqual(fluxo.tile_de(meio[0], meio[1]), (x, y))
        self.assertGreater(pontos[0][0], pontos[2][0])               # y do pedaço cresce para o SUL
        self.assertLess(pontos[0][1], pontos[2][1])                  # x cresce para o leste

    def test_guarda_pede_so_o_que_falta_e_para_se_a_chave_for_recusada(self):
        pedidos = []

        def baixar(url, timeout):
            pedidos.append(url)
            return b""                                              # pedaço vazio (sem ruas medidas)
        f = fluxo.Fluxo(baixar)
        f.buscar_tile("CHAVE", 1487, 2238)
        self.assertIn("/tile/flow/relative/12/1487/2238.pbf?key=CHAVE&roadTypes=%5B0,1,2,3,4%5D", pedidos[0])
        self.assertEqual(f.faltam([(1487, 2238), (1488, 2238)]), [(1488, 2238)])
        self.assertEqual(f.faltam([(1487, 2238)], agora=1e12), [(1487, 2238)])       # venceu: pede de novo
        self.assertEqual(f.segmentos([(1487, 2238), (9, 9)]), [])

        def recusa(url, timeout):
            raise urllib.error.HTTPError("x", 403, "Forbidden", None, None)
        g = fluxo.Fluxo(recusa)
        with self.assertRaises(fluxo.SemChave):
            g.buscar_tile("CHAVE", 1, 1)
        self.assertTrue(g.recusada)
        self.assertFalse(g.atualizar("CHAVE", [(1, 1)], lambda mudou: None))        # não insiste


class TesteEndereco(unittest.TestCase):
    def test_monta_rua_numero_e_bairro(self):
        pedidos = []
        resposta = {"addresses": [{"address": {"streetName": "Rua 9", "streetNumber": "250",
                                               "municipalitySubdivision": "Setor Oeste"}}]}

        def baixar(url, timeout):
            pedidos.append(url)
            return json.dumps(resposta).encode("utf-8")
        self.assertEqual(busca.endereco_de(-16.70, -49.26, "CHAVE", baixar), "Rua 9, 250 - Setor Oeste")
        self.assertIn("/search/2/reverseGeocode/-16.700000,-49.260000.json?", pedidos[0])
        self.assertIn("language=pt-BR", pedidos[0])

    def test_sem_rua_ou_sem_chave(self):
        vazio = json.dumps({"addresses": [{"address": {"municipality": "Goiânia"}}]}).encode("utf-8")
        self.assertEqual(busca.endereco_de(-16.7, -49.2, "CHAVE", lambda u, t: vazio), "")
        import chaves
        original, chaves._cache = chaves._cache, {}
        chamado = []
        try:
            self.assertEqual(busca.endereco_de(-16.7, -49.2, None, lambda u, t: chamado.append(u)), "")
        finally:
            chaves._cache = original
        self.assertEqual(chamado, [])                                # sem chave nem tenta


if __name__ == "__main__":
    unittest.main()
