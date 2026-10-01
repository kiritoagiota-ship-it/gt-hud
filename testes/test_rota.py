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
