import unittest

import rota as rotas
from testes.apoio import rota_reta


def codificar_polyline(pontos, precisao=1e6):
    """O contrário de rota.decodificar_polyline (só para o teste)."""
    saida, ult = [], (0, 0)
    for lat, lon in pontos:
        atual = (int(round(lat * precisao)), int(round(lon * precisao)))
        for v in (atual[0] - ult[0], atual[1] - ult[1]):
            v = ~(v << 1) if v < 0 else v << 1
            while v >= 0x20:
                saida.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            saida.append(chr(v + 63))
        ult = atual
    return "".join(saida)


class TesteRota(unittest.TestCase):
    def test_polyline_ida_e_volta(self):
        pontos = [(-16.680123, -49.255321), (-16.681, -49.2561), (-16.7, -49.3)]
        volta = rotas.decodificar_polyline(codificar_polyline(pontos))
        for a, b in zip(pontos, volta):
            self.assertAlmostEqual(a[0], b[0], places=6)
            self.assertAlmostEqual(a[1], b[1], places=6)

    def test_subida_e_descida(self):
        # 300 m plano, 300 m subindo 8%, 300 m plano, 300 m descendo 6%
        e = [800.0] * 11 + [800 + 2.4 * k for k in range(1, 11)] + [824.0] * 10 \
            + [824 - 1.8 * k for k in range(1, 11)] + [806.0] * 3
        sub = rotas.achar_subidas(e)
        self.assertEqual(len(sub), 1)
        self.assertAlmostEqual(sub[0]["grau"], 8, delta=1.5)
        r = rota_reta(len(e) * 30 - 30, elevacao=e)
        self.assertEqual(len(r.descidas), 1)
        self.assertAlmostEqual(r.descidas[0]["grau"], 6, delta=1.5)
        self.assertAlmostEqual(r.subida_total_m, 24, delta=1)

    def test_ponto_em(self):
        r = rota_reta(600)
        lat, lon, rumo = r.ponto_em(300)
        self.assertAlmostEqual(rotas.distancia_m(r.pontos[0], (lat, lon)), 300, delta=1)
        self.assertAlmostEqual(rumo, 0, delta=1)  # para o norte
        self.assertEqual(r.ponto_em(10000)[:2], r.pontos[-1])

    def test_parecidas_e_nomes_pelos_numeros(self):
        a = rota_reta(1000, tempo_s=200)
        b = rota_reta(1000, tempo_s=205)
        c = rota_reta(800, tempo_s=230, lon0=-49.24)  # outro caminho, mais curto e mais lento
        self.assertTrue(rotas.parecidas(a, b))
        self.assertFalse(rotas.parecidas(a, c))
        lista = rotas.rotular([a, c])
        self.assertEqual([r.nome_perfil for r in lista], ["Mais rápida", "Mais curta"])
        d = rota_reta(1000, tempo_s=260, lon0=-49.23)  # pior em tudo: sai da lista
        self.assertEqual(len(rotas.rotular([a, d])), 1)


if __name__ == "__main__":
    unittest.main()


class TesteRotaTranquila(unittest.TestCase):
    """A rota calma é escolhida MEDINDO o estresse de cada opção (classe da
    via, faixas, limite) e contornando as avenidas achadas."""

    def setUp(self):
        self._principal, self._enviar = rotas._pedir_principal, rotas.rede.enviar

    def tearDown(self):
        rotas._pedir_principal, rotas.rede.enviar = self._principal, self._enviar

    def _medidor(self, por_rota):
        """rede.enviar de mentira: uma avenida no começo da rota (fração dada
        pela longitude dela) e rua de bairro no resto."""
        def enviar(url, corpo, metodo="PUT", timeout=20):
            pontos = rotas.decodificar_polyline(corpo["encoded_polyline"])
            avenida = por_rota[round(pontos[0][1], 3)]
            n = len(pontos) - 1
            corte = int(round(n * avenida))
            km = n * 0.01
            trechos = []
            if corte:
                trechos.append({"road_class": "primary", "lane_count": 2, "length": km * avenida,
                                "begin_shape_index": 0, "end_shape_index": corte, "names": ["Avenida Grande"]})
            trechos.append({"road_class": "residential", "length": km * (1 - avenida),
                            "begin_shape_index": corte, "end_shape_index": n, "names": ["Rua Calma"]})
            return {"edges": trechos, "shape": corpo["encoded_polyline"]}
        return enviar

    def test_niveis(self):
        n = rotas.nivel_do_trecho
        self.assertEqual(n({"road_class": "residential"}), 0)
        self.assertEqual(n({"road_class": "tertiary"}), 1)
        self.assertEqual(n({"road_class": "secondary", "lane_count": 1}), 1)
        self.assertEqual(n({"road_class": "secondary", "lane_count": 2}), 2)
        self.assertEqual(n({"road_class": "secondary", "lane_count": 1, "speed_limit": 60}), 3)
        self.assertEqual(n({"road_class": "primary", "lane_count": 1}), 2)
        self.assertEqual(n({"road_class": "primary", "lane_count": 3}), 3)
        self.assertEqual(n({"road_class": "trunk"}), 3)
        self.assertEqual(n({"road_class": "primary", "lane_count": 3, "cycle_lane": "separated"}), 0)

    def test_medida_guarda_trechos_e_avenidas(self):
        r = rota_reta(3000, tempo_s=600, lon0=-49.250)
        rotas.rede.enviar = self._medidor({-49.250: 0.40})
        self.assertAlmostEqual(rotas.medir_movimento(r), 0.40, places=2)
        self.assertAlmostEqual(r.estresse, 0.40 * 6.0, places=1)        # avenida de 2 faixas: nível 3
        self.assertEqual(len(r.trechos), 1)
        self.assertEqual(r.trechos[0][1], 3)
        inicio, fim, nivel, nome = r.avenidas[0]
        self.assertEqual((round(inicio), nivel, nome), (0, 3, "Avenida Grande"))
        self.assertAlmostEqual(fim, 1200, delta=15)

    def test_escolhe_a_de_menor_estresse_e_tenta_contornar(self):
        rapida = rota_reta(3000, tempo_s=600, lon0=-49.250)
        igual = rota_reta(3000, tempo_s=600, lon0=-49.250)       # o servidor devolveu a mesma
        calma = rota_reta(3400, tempo_s=720, lon0=-49.260)
        longa = rota_reta(9000, tempo_s=2400, lon0=-49.270)      # calmíssima, mas 4x o tempo
        contorno = rota_reta(3600, tempo_s=760, lon0=-49.280)    # o que volta ao mandar evitar as avenidas
        pedidos = []

        def principal(origem, destino, rumo, nome, perfil, alternativas=0, evitar=()):
            pedidos.append(len(evitar))
            return [igual, calma, longa] if alternativas else contorno
        rotas._pedir_principal = principal
        rotas.rede.enviar = self._medidor({-49.250: 0.80, -49.260: 0.30, -49.270: 0.05, -49.280: 0.05})
        escolhida = rotas.mais_tranquila((-16.0, -49.0), (-17.0, -50.0), rapida=rapida, esperar=lambda s: None)
        self.assertIs(escolhida, contorno)                       # a que contornou as avenidas ganhou
        self.assertGreater(pedidos[1], 0)                        # mandou evitar pontos
        self.assertAlmostEqual(rapida.movimentada, 0.80, places=2)
        self.assertIsNone(igual.movimentada)                     # igual à rápida: nem perguntou

    def test_contorno_pior_nao_substitui(self):
        rapida = rota_reta(3000, tempo_s=600, lon0=-49.250)
        calma = rota_reta(3400, tempo_s=720, lon0=-49.260)
        pior = rota_reta(3600, tempo_s=760, lon0=-49.280)
        rotas._pedir_principal = lambda o, d, r, n, p, alternativas=0, evitar=(): [calma] if alternativas else pior
        rotas.rede.enviar = self._medidor({-49.250: 0.80, -49.260: 0.30, -49.280: 0.60})
        self.assertIs(rotas.mais_tranquila((-16.0, -49.0), (-17.0, -50.0), rapida=rapida,
                                           esperar=lambda s: None), calma)

    def test_nomes_pela_medida(self):
        rapida = rota_reta(3000, tempo_s=600, lon0=-49.250)
        calma = rota_reta(3400, tempo_s=720, lon0=-49.260)
        calma.perfil = "tranquila"
        rapida.movimentada, rapida.estresse = 0.80, 4.8
        calma.movimentada, calma.estresse = 0.25, 1.5
        lista = rotas.rotular([rapida, calma])
        self.assertEqual([r.nome_perfil for r in lista], ["Mais rápida", "Mais tranquila"])
        # "tranquila" que não é mais calma de verdade não entra, e a pessoa fica sabendo
        falsa = rota_reta(3400, tempo_s=720, lon0=-49.260)
        falsa.perfil = "tranquila"
        rapida.movimentada, rapida.estresse = 0.50, 3.0
        falsa.movimentada, falsa.estresse = 0.48, 2.9
        lista = rotas.rotular([rapida, falsa])
        self.assertEqual([r.nome_perfil for r in lista], ["Mais rápida (não achei mais calma)"])

    def test_sem_conseguir_medir_fica_com_a_primeira(self):
        rapida = rota_reta(3000, tempo_s=600, lon0=-49.250)
        a = rota_reta(3400, tempo_s=720, lon0=-49.260)

        def caiu(*x, **k):
            raise OSError("sem internet")
        rotas._pedir_principal = lambda *x, **k: [a]
        rotas.rede.enviar = caiu
        self.assertIs(rotas.mais_tranquila((0, 0), (1, 1), rapida=rapida, esperar=lambda s: None), a)
        self.assertIsNone(a.movimentada)


class TesteAvisoDeAvenida(unittest.TestCase):
    def test_avisa_antes_de_entrar_e_mostra_no_chip(self):
        from navegacao import Navegacao
        from testes.apoio import Fala
        rota = rota_reta(1500)
        rota.avenidas = [(400.0, 1100.0, 3, "Avenida Grande"), (1200.0, 1300.0, 2, "Curtinha")]
        fala = Fala()
        nav = Navegacao(rota, fala)
        self.assertEqual(len(nav.avenidas), 1)                   # a de 100 m não merece aviso
        agora, vistos = 0.0, []
        for k in range(0, 140):
            lat, lon = rota.pontos[min(k, len(rota.pontos) - 1)]
            agora += 1.2
            e = nav.atualizar(lat, lon, 30.0, agora)
            if e["alerta"] and e["alerta"]["tipo"] == "avenida":
                vistos.append((round(nav.dist_feita), round(e["alerta"]["em_m"]), round(e["alerta"]["falta_m"])))
        ditas = [t for t in fala.textos() if "Avenida Grande" in t]
        self.assertEqual(ditas, ["Atenção: Avenida Grande à frente, de trânsito pesado, por 700 metros."])
        self.assertTrue(any(em > 0 for _, em, _ in vistos))      # "Avenida em X m" antes
        self.assertTrue(any(em == 0 and falta < 700 for _, em, falta in vistos))   # "Em avenida: faltam X"
