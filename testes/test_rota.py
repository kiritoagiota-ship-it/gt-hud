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
    """A rota calma é escolhida MEDINDO quanto de avenida cada opção tem."""

    def setUp(self):
        self._principal, self._enviar = rotas._pedir_principal, rotas.rede.enviar

    def tearDown(self):
        rotas._pedir_principal, rotas.rede.enviar = self._principal, self._enviar

    def _medidor(self, por_rota):
        """rede.enviar de mentira: devolve os trechos conforme a rota perguntada."""
        def enviar(url, corpo, metodo="PUT", timeout=20):
            pontos = rotas.decodificar_polyline(corpo["encoded_polyline"])
            chave = round(pontos[0][1], 3)       # as rotas de teste diferem na longitude
            avenida = por_rota[chave]
            return {"edges": [{"road_class": "primary", "length": avenida},
                              {"road_class": "residential", "length": 1.0 - avenida}]}
        return enviar

    def test_escolhe_a_alternativa_com_menos_avenida(self):
        rapida = rota_reta(3000, tempo_s=600, lon0=-49.250)
        igual = rota_reta(3000, tempo_s=600, lon0=-49.250)       # o servidor devolveu a mesma
        calma = rota_reta(3400, tempo_s=720, lon0=-49.260)
        longa = rota_reta(9000, tempo_s=2400, lon0=-49.270)      # calmíssima, mas 4x o tempo
        rotas._pedir_principal = lambda *a, **k: [igual, calma, longa]
        rotas.rede.enviar = self._medidor({-49.250: 0.80, -49.260: 0.25, -49.270: 0.05})
        escolhida = rotas.mais_tranquila((0, 0), (1, 1), rapida=rapida, esperar=lambda s: None)
        self.assertIs(escolhida, calma)
        self.assertAlmostEqual(rapida.movimentada, 0.80)
        self.assertAlmostEqual(calma.movimentada, 0.25)
        self.assertAlmostEqual(igual.movimentada, 0.80)          # igual à rápida: nem perguntou

    def test_nomes_pela_medida(self):
        rapida = rota_reta(3000, tempo_s=600, lon0=-49.250)
        calma = rota_reta(3400, tempo_s=720, lon0=-49.260)
        calma.perfil = "tranquila"
        rapida.movimentada, calma.movimentada = 0.80, 0.25
        lista = rotas.rotular([rapida, calma])
        self.assertEqual([r.nome_perfil for r in lista], ["Mais rápida", "Mais tranquila"])
        # "tranquila" que não é mais calma de verdade não entra, e a pessoa fica sabendo
        falsa = rota_reta(3400, tempo_s=720, lon0=-49.260)
        falsa.perfil = "tranquila"
        rapida.movimentada, falsa.movimentada = 0.50, 0.48
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
