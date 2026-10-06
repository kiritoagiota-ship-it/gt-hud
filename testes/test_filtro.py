"""Filtro do velocímetro: acompanha acelerada e freada sem tremer parado."""
import math
import random
import unittest

from filtro import FiltroVelocidade


def _rampa(t):
    """m/s: parado 5 s, acelera até 9 m/s (32 km/h) em 8 s, mantém."""
    if t < 5:
        return 0.0
    return min(9.0, (t - 5) * 9.0 / 8.0)


class TesteFiltro(unittest.TestCase):
    def test_ritmo_constante_fica_firme(self):
        rnd = random.Random(1)
        f = FiltroVelocidade()
        saidas = [f.atualizar(7.0 + rnd.gauss(0, 0.3), t=float(t), incerteza_ms=0.3) for t in range(1, 60)]
        fim = saidas[20:]
        self.assertAlmostEqual(sum(fim) / len(fim), 25.2, delta=0.5)
        self.assertLess(max(fim) - min(fim), 3.6)   # a leitura crua varia uns 5 km/h aqui

    def test_acelerada_sem_atraso_grande(self):
        f = FiltroVelocidade()
        pior = pior_antigo = 0.0
        antigo = 0.0   # a média móvel de antes (alfa 0,5), para comparar
        for t in range(1, 20):
            # o GPS entrega a média do segundo que passou
            z = sum(_rampa(t - k / 10.0) for k in range(11)) / 11.0
            v = f.atualizar(z, t=float(t), incerteza_ms=0.2)
            antigo = 0.5 * z * 3.6 + 0.5 * antigo
            if t >= 7:   # antes disso está abaixo do limiar de "parado"
                pior = max(pior, abs(v - _rampa(t) * 3.6))
                pior_antigo = max(pior_antigo, abs(antigo - _rampa(t) * 3.6))
        self.assertLess(pior, 2.5)
        self.assertGreater(pior_antigo, 2 * pior)

    def test_parou_zera_logo(self):
        f = FiltroVelocidade()
        for t in range(1, 10):
            f.atualizar(6.0, t=float(t))
        f.atualizar(0.1, t=10.0)
        self.assertEqual(f.atualizar(0.05, t=11.0), 0.0)

    def test_pulo_impossivel_quase_nao_conta(self):
        f = FiltroVelocidade()
        for t in range(1, 15):
            f.atualizar(5.0, t=float(t), incerteza_ms=0.2)
        v = f.atualizar(30.0, t=15.0, incerteza_ms=0.2)   # 18 -> 108 km/h em 1 s
        self.assertLess(v, 30.0)

    def test_leitura_ruim_pesa_menos(self):
        boa, ruim = FiltroVelocidade(), FiltroVelocidade()
        for t in range(1, 15):
            boa.atualizar(5.0, t=float(t), incerteza_ms=0.2)
            ruim.atualizar(5.0, t=float(t), incerteza_ms=0.2)
        self.assertGreater(boa.atualizar(6.5, t=15.0, incerteza_ms=0.15),
                           ruim.atualizar(6.5, t=15.0, incerteza_ms=2.0))

    def test_buraco_no_sinal_recomeca(self):
        f = FiltroVelocidade()
        for t in range(1, 10):
            f.atualizar(8.0, t=float(t))
        self.assertAlmostEqual(f.atualizar(3.0, t=30.0), 10.8, places=3)

    def test_sem_hora_nem_incerteza_funciona(self):
        f = FiltroVelocidade()
        self.assertAlmostEqual(f.atualizar(5.0), 18.0, places=3)
        self.assertFalse(math.isnan(f.atualizar(5.2)))


if __name__ == "__main__":
    unittest.main()
