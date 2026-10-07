"""Chuva no caminho, aprendizado com as viagens e trânsito ao vivo."""
import json
import os
import tempfile
import time
import unittest
import urllib.error

import aprendizado
import clima
import transito
from testes.apoio import rota_reta

M_GRAU = 111320.0


class TesteChuva(unittest.TestCase):
    def _prever(self, na_saida, no_destino):
        def prever(lat, lon):
            return na_saida if lat > -16.69 else no_destino
        return prever

    def test_sem_chuva(self):
        seco = [(k * 15, 0.0, 10.0) for k in range(9)]
        self.assertIsNone(clima.chuva((-16.68, -49.25), (-16.70, -49.27), 1200, self._prever(seco, seco)))

    def test_chuva_no_destino_dentro_do_tempo_de_chegada(self):
        seco = [(k * 15, 0.0, 10.0) for k in range(9)]
        molhado = [(0, 0.0, 20.0), (15, 0.0, 30.0), (30, 0.8, 80.0), (45, 3.0, 90.0)]
        c = clima.chuva((-16.68, -49.25), (-16.70, -49.27), 1200, self._prever(seco, molhado))
        self.assertEqual(c, {"em_min": 30, "onde": "destino", "forte": False})
        self.assertEqual(clima.frase(c), "Chuva prevista em ~30 min no destino")
        self.assertEqual(clima.fala(c), "Atenção: previsão de chuva em 30 minutos no destino.")

    def test_chuva_depois_da_chegada_nao_avisa(self):
        seco = [(k * 15, 0.0, 10.0) for k in range(9)]
        tarde = [(k * 15, 0.0 if k < 6 else 2.5, 10.0) for k in range(9)]     # só daqui a 90 min
        self.assertIsNone(clima.chuva((-16.68, -49.25), (-16.70, -49.27), 600, self._prever(seco, tarde)))

    def test_chovendo_forte_agora_na_saida(self):
        agora = [(0, 2.6, 95.0), (15, 1.0, 80.0)]
        seco = [(k * 15, 0.0, 10.0) for k in range(9)]
        c = clima.chuva((-16.68, -49.25), (-16.70, -49.27), 1200, self._prever(agora, seco))
        self.assertEqual((c["em_min"], c["onde"], c["forte"]), (0, "saida", True))
        self.assertEqual(clima.frase(c), "Chuva forte prevista agora na saída")


class TesteAprendizado(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.a = aprendizado.Aprendizado(os.path.join(self.pasta.name, "t.db"))
        self.t0 = time.mktime((2026, 10, 7, 14, 0, 0, 0, 0, -1))      # quarta à tarde

    def tearDown(self):
        self.pasta.cleanup()

    def _viagem(self, rota, vel_ms, t0, lento=None):
        """Pontos de 1 em 1 s andando a rota; `lento` = (início m, fim m, m/s)."""
        pontos, d, t = [], 0.0, t0
        while d < rota.total_m:
            v = lento[2] if (lento and lento[0] <= d < lento[1]) else vel_ms
            lat, lon, _ = rota.ponto_em(d)
            pontos.append((lat, lon, v * 3.6, t))
            d += v
            t += 1.0
        return pontos

    def test_precisa_de_duas_passagens(self):
        rota = rota_reta(3000, tempo_s=600)
        self.a.aprender(self._viagem(rota, 8.0, self.t0))
        self.assertEqual(self.a.avaliar(rota, self.t0)["cobertura"], 0.0)
        self.a.aprender(self._viagem(rota, 8.0, self.t0 + 86400))
        r = self.a.avaliar(rota, self.t0)
        self.assertGreater(r["cobertura"], 0.9)
        self.assertAlmostEqual(r["tempo_s"], 3000 / 8.0, delta=20)     # o tempo DELE, não os 600 s do servidor
        self.assertEqual(r["lentos"], [])

    def test_trecho_que_costuma_estar_lento(self):
        rota = rota_reta(3000, tempo_s=600)
        for dia in range(3):
            self.a.aprender(self._viagem(rota, 8.0, self.t0 + dia * 86400, lento=(1000, 1500, 1.5)))
        r = self.a.avaliar(rota, self.t0)
        self.assertEqual(len(r["lentos"]), 1)
        inicio, fim = r["lentos"][0]
        self.assertAlmostEqual(inicio, 1000, delta=160)
        self.assertAlmostEqual(fim, 1500, delta=160)
        self.assertGreater(r["extra_s"], 150)                          # ~500 m a 1,5 m/s em vez de ~6
        self.assertGreater(r["tempo_s"], 3000 / 8.0 + 150)

    def test_rota_que_ele_pouco_conhece_fica_com_o_tempo_do_servidor(self):
        conhecida = rota_reta(600, tempo_s=120)
        for dia in range(2):
            self.a.aprender(self._viagem(conhecida, 8.0, self.t0 + dia * 86400))
        longa = rota_reta(6000, tempo_s=1200)                          # só os primeiros 10% são conhecidos
        r = self.a.avaliar(longa, self.t0)
        self.assertLess(r["cobertura"], 0.3)
        self.assertIsNone(r["tempo_s"])

    def test_parada_longa_nao_vira_transito(self):
        rota = rota_reta(1200, tempo_s=240)
        for dia in range(2):
            pontos = self._viagem(rota, 8.0, self.t0 + dia * 86400)
            meio = pontos[len(pontos) // 2]
            parado = [(meio[0], meio[1], 0.0, meio[3] + k) for k in range(1, 601)]     # 10 min parado
            depois = [(p[0], p[1], p[2], p[3] + 600) for p in pontos[len(pontos) // 2 + 1:]]
            self.a.aprender(pontos[:len(pontos) // 2 + 1] + parado + depois)
        r = self.a.avaliar(rota, self.t0)
        self.assertLess(r["tempo_s"], 1200 / 8.0 + 120)                # só ~90 s da parada contam

    def test_faixas_de_horario(self):
        self.assertEqual(aprendizado.faixa_de(time.mktime((2026, 10, 7, 7, 30, 0, 0, 0, -1))), 1)    # quarta, pico da manhã
        self.assertEqual(aprendizado.faixa_de(time.mktime((2026, 10, 7, 18, 0, 0, 0, 0, -1))), 3)    # pico da tarde
        self.assertEqual(aprendizado.faixa_de(time.mktime((2026, 10, 10, 18, 0, 0, 0, 0, -1))), 8)   # sábado


class TesteTransito(unittest.TestCase):
    def setUp(self):
        transito.esquecer()
        self.rota = rota_reta(2000)                                    # para o norte, a partir de -16.68, -49.25

    def _ponto(self, metros, lado_m=0.0):
        return [-49.25 + lado_m / (M_GRAU * 0.958), -16.68 + metros / M_GRAU]     # [lon, lat]

    def _resposta(self, *itens):
        return json.dumps({"incidents": list(itens)}).encode("utf-8")

    def _linha(self, de, ate, categoria=6, magnitude=2, atraso=120, lado_m=0.0, **props):
        passo = 40 if ate > de else -40
        coords = [self._ponto(m, lado_m) for m in range(de, ate, passo)] + [self._ponto(ate, lado_m)]
        return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
                "properties": dict({"iconCategory": categoria, "magnitudeOfDelay": magnitude, "delay": atraso,
                                    "length": abs(ate - de), "events": [{"description": "Trânsito parado"}]}, **props)}

    def test_le_a_resposta_e_acha_o_que_esta_na_rota(self):
        acidente = {"type": "Feature", "geometry": {"type": "Point", "coordinates": self._ponto(1500)},
                    "properties": {"iconCategory": 1, "magnitudeOfDelay": 3, "delay": 0,
                                   "events": [{"description": "Acidente"}]}}
        dados = self._resposta(
            self._linha(400, 900),                                     # trânsito lento na rota, no sentido dela
            self._linha(1200, 700, atraso=300),                        # na outra pista (sentido contrário)
            self._linha(400, 900, lado_m=300.0),                       # numa rua paralela, 300 m ao lado
            acidente,
            self._linha(100, 300, categoria=4))                        # "chuva": categoria que o app não usa
        ocorrencias = transito.buscar("CHAVE", baixar=lambda url, timeout: dados)
        self.assertEqual(len(ocorrencias), 4)
        achadas = transito.avaliar(self.rota, ocorrencias)
        self.assertEqual([a["categoria"] for a in achadas], [6, 1])
        lento = achadas[0]
        self.assertAlmostEqual(lento["inicio_m"], 400, delta=12)
        self.assertAlmostEqual(lento["fim_m"], 900, delta=12)
        self.assertAlmostEqual(self.rota.atraso_transito_s, 120 * transito.ATRASO_MOTO, delta=8)
        self.assertFalse(self.rota.interditada)
        self.assertEqual(len(self.rota.trechos_transito), 1)           # o acidente é um ponto: não pinta trecho
        self.assertEqual(transito.resumo(self.rota), "+1 min de trânsito, acidente")

    def test_via_interditada(self):
        dados = self._resposta(self._linha(600, 800, categoria=8, magnitude=4, atraso=0))
        transito.avaliar(self.rota, transito.buscar("CHAVE", baixar=lambda url, timeout: dados))
        self.assertTrue(self.rota.interditada)
        self.assertEqual(transito.resumo(self.rota), "Via interditada no caminho")

    def test_rota_livre(self):
        transito.avaliar(self.rota, [])
        self.assertEqual((self.rota.incidentes, self.rota.atraso_transito_s, transito.resumo(self.rota)), ([], 0, ""))

    def test_chave_recusada_e_a_chave_nao_aparece_no_erro(self):
        def recusa(url, timeout):
            raise urllib.error.HTTPError("https://api.tomtom.com/...", 403, "Forbidden", None, None)
        with self.assertRaises(transito.SemChave) as c:
            transito.buscar("MINHA-CHAVE-SECRETA", baixar=recusa)
        self.assertNotIn("MINHA-CHAVE-SECRETA", str(c.exception))

    def test_guarda_a_cidade_por_tres_minutos(self):
        pedidos = []

        def baixar(url, timeout):
            pedidos.append(url)
            return self._resposta()
        transito.da_cidade("CHAVE", agora=1000.0, baixar=baixar)
        transito.da_cidade("CHAVE", agora=1100.0, baixar=baixar)       # 100 s depois: não pergunta de novo
        self.assertEqual(len(pedidos), 1)
        transito.da_cidade("CHAVE", agora=1000.0 + transito.VALIDADE_S + 1, baixar=baixar)
        self.assertEqual(len(pedidos), 2)
        self.assertIn("bbox=-49.45000%2C-16.86000%2C-49.07000%2C-16.48000", pedidos[0])   # lon, lat, lon, lat


if __name__ == "__main__":
    unittest.main()
