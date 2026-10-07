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

    def test_arrancada_nao_espera(self):
        f = FiltroVelocidade()
        for t in range(1, 6):
            f.atualizar(0.0, t=float(t), idade_s=0.4, agora=t + 0.4)       # parado no semáforo
        v = f.atualizar(1.2, t=6.0, idade_s=0.4, agora=6.4)                # saiu: média de 0 a 2,4 m/s
        self.assertGreater(v, 4.3)                                         # já mostra o que leu (4,3 km/h) ou mais
        self.assertGreater(f.previsto(7.0), v)                             # e segue subindo até a próxima leitura

    def test_entre_leituras_segue_a_tendencia_e_para_sem_gps(self):
        f = FiltroVelocidade()
        for t in range(1, 9):
            f.atualizar(1.0 * t, t=float(t), idade_s=0.3, agora=t + 0.3)   # acelerando 1 m/s2
        logo, depois = f.previsto(8.4), f.previsto(9.2)
        self.assertGreater(depois, logo + 0.5)                             # o número anda sem leitura nova
        self.assertAlmostEqual(f.previsto(60.0), f.previsto(9.6), places=3)   # GPS sumiu: para de prever
        parado = FiltroVelocidade()
        for t in range(1, 9):
            parado.atualizar(7.0, t=float(t), idade_s=0.3, agora=t + 0.3)
        self.assertAlmostEqual(parado.previsto(8.9), parado.previsto(8.3), delta=0.3)   # ritmo constante: quieto

    def test_ajuste_para_igualar_ao_painel(self):
        real, painel = FiltroVelocidade(), FiltroVelocidade()
        painel.ajuste = 1.08
        for t in range(1, 12):
            a = real.atualizar(8.0, t=float(t))
            b = painel.atualizar(8.0, t=float(t))
        self.assertAlmostEqual(b / a, 1.08, places=3)
        self.assertAlmostEqual(a, 28.8, delta=0.3)                         # sem ajuste: a velocidade do GPS


if __name__ == "__main__":
    unittest.main()
