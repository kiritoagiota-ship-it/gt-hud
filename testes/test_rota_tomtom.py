"""Rotas da TomTom (com o trânsito de agora): leitura da resposta e conferência do caminho."""
import json
import unittest

import rota as rotas
import rota_tomtom
from testes.apoio import Fala, rota_reta

M = 1.0 / 111320.0


def _resposta(*lista):
    return {"routes": list(lista)}


def _rota(pontos, tempo, livre=None, metros=None, instrucoes=()):
    return {"summary": {"lengthInMeters": metros if metros is not None else 0, "travelTimeInSeconds": tempo,
                        "noTrafficTravelTimeInSeconds": livre if livre is not None else tempo,
                        "trafficDelayInSeconds": 0},
            "legs": [{"points": [{"latitude": a, "longitude": b} for a, b in pontos]}],
            "guidance": {"instructions": list(instrucoes)}}


class TestePedir(unittest.TestCase):
    def test_le_pontos_manobras_tempo_e_relevo(self):
        pontos = [(-16.68 + k * 100 * M, -49.25) for k in range(6)] + [(-16.68 + 500 * M, -49.25 + 300 * M)]
        instrucoes = [
            {"maneuver": "DEPART", "pointIndex": 0, "message": "Saia pela Rua 1", "street": "Rua 1"},
            {"maneuver": "FOLLOW", "pointIndex": 2, "message": "Siga"},                       # não vira aviso
            {"maneuver": "TURN_RIGHT", "pointIndex": 5, "message": "Vire à direita na Rua 2", "street": "Rua 2"},
            {"maneuver": "ROUNDABOUT_LEFT", "pointIndex": 5, "roundaboutExitNumber": 3, "message": "Na rotatória"},
            {"maneuver": "ARRIVE_LEFT", "pointIndex": 99, "message": "Chegou"}]            # índice fora: prende no fim
        pedidos = []

        def baixar(url, timeout):
            pedidos.append(url)
            return json.dumps(_resposta(_rota(pontos, 420, livre=300, instrucoes=instrucoes))).encode("utf-8")
        r = rota_tomtom.pedir("CHAVE", pontos[0], pontos[-1], rumo=370, destino_nome="Casa", baixar=baixar,
                              elevacao_de=lambda p: [800.0, 801.0, 803.0])
        self.assertEqual(len(r.pontos), 7)
        self.assertEqual([m["acao"] for m in r.manobras],
                         ["em_frente", "direita", "rotatoria", "chegada_esquerda"])
        self.assertEqual((r.manobras[1]["ruas"], r.manobras[2]["saida"], r.manobras[3]["indice"]), ("Rua 2", 3, 6))
        self.assertAlmostEqual(r.manobras[1]["dist_m"], 500, delta=5)
        self.assertEqual((r.perfil, r.nome_perfil, r.elevacao),
                         ("transito", "Pelo trânsito de agora", [800.0, 801.0, 803.0]))
        self.assertEqual(r.tempo_s, 420)                 # o tempo da TomTom, sem o "ritmo" das rotas de bike
        r.atraso_transito_s = 99.0
        self.assertEqual(r.tempo_s, 420)                 # e sem somar de novo o atraso das ocorrências
        url = pedidos[0]
        self.assertIn("/routing/1/calculateRoute/-16.680000,-49.250000:", url)
        for parte in ("travelMode=car", "traffic=true", "vehicleMaxSpeed=50", "avoid=motorways", "language=pt-BR",
                      "instructionsType=text", "computeTravelTimeFor=all", "vehicleHeading=10"):
            self.assertIn(parte, url)

    def test_sem_caminho_e_sem_relevo(self):
        vazio = json.dumps(_resposta()).encode("utf-8")
        self.assertIsNone(rota_tomtom.pedir("C", (0, 0), (1, 1), baixar=lambda u, t: vazio))

        def sem_relevo(p):
            raise OSError("servidor do relevo fora")
        pontos = [(-16.68, -49.25), (-16.681, -49.25)]
        r = rota_tomtom.pedir("C", pontos[0], pontos[1], elevacao_de=sem_relevo,
                              baixar=lambda u, t: json.dumps(_resposta(_rota(pontos, 60))).encode("utf-8"))
        self.assertEqual((r.elevacao, r.subidas), ([], []))


class TesteConferir(unittest.TestCase):
    def setUp(self):
        self.rota = rota_reta(3000, tempo_s=600)

    def _enviar(self, resposta, guardar=None):
        def enviar(url, corpo, metodo, timeout):
            if guardar is not None:
                guardar.append((url, corpo, metodo))
            return resposta
        return enviar

    def test_atraso_do_caminho_atual_e_caminho_melhor(self):
        resto = [self.rota.ponto_em(d)[:2] for d in range(1000, 3001, 100)]
        outra = [resto[0], (resto[0][0], resto[0][1] + 400 * M), resto[-1]]
        guardado = []
        resposta = _resposta(_rota(resto, 700, livre=400, metros=2000), _rota(outra, 380, metros=2300))
        r = rota_tomtom.conferir("CHAVE", self.rota, 1000.0, resto[0], rumo=0, enviar=self._enviar(resposta, guardado))
        self.assertEqual((r["atraso_s"], r["falta_s"], r["ganho_s"]), (300, 700, 320))
        self.assertEqual(r["melhor"].perfil, "transito")
        url, corpo, metodo = guardado[0]
        self.assertEqual(metodo, "POST")
        apoio = corpo["supportingPoints"]
        self.assertAlmostEqual(apoio[0]["latitude"], resto[0][0], places=6)      # começa onde ele está
        self.assertAlmostEqual(apoio[-1]["latitude"], self.rota.pontos[-1][0], places=6)   # termina no destino
        self.assertLessEqual(len(apoio), rota_tomtom.PONTOS_APOIO_MAX + 2)
        for parte in ("maxAlternatives=1", "alternativeType=betterRoute", "minDeviationTime=150"):
            self.assertIn(parte, url)

    def test_ganho_pequeno_nao_vira_sugestao(self):
        resto = [self.rota.ponto_em(d)[:2] for d in range(0, 3001, 100)]
        resposta = _resposta(_rota(resto, 700, livre=650, metros=3000),
                             _rota(resto[:2] + resto[-1:], 640, metros=3100))
        r = rota_tomtom.conferir("C", self.rota, 0.0, resto[0], enviar=self._enviar(resposta))
        self.assertEqual((r["atraso_s"], r["melhor"]), (50, None))

    def test_tomtom_refez_outro_caminho(self):
        resto = [self.rota.ponto_em(d)[:2] for d in range(0, 3001, 100)]
        resposta = _resposta(_rota(resto, 700, metros=4200))      # 40% mais longo: não é o caminho dele
        self.assertIsNone(rota_tomtom.conferir("C", self.rota, 0.0, resto[0], enviar=self._enviar(resposta)))


class TesteTempoAoVivo(unittest.TestCase):
    def test_tempo_que_falta_usa_o_transito_de_agora(self):
        from navegacao import Navegacao
        rota = rota_reta(3000, tempo_s=600)
        nav = Navegacao(rota, Fala())
        lat, lon, _ = rota.ponto_em(1000)
        e = nav.atualizar(lat, lon, 30.0, 10.0)
        livre = e["restante_s"]
        self.assertAlmostEqual(livre, rota.tempo_s * 2000 / 3000, delta=3)
        nav.definir_vivo(240.0, 999.0)                      # 4 min de trânsito nos 2 km que faltam
        e = nav.atualizar(lat, lon, 30.0, 11.0)
        self.assertAlmostEqual(e["restante_s"], livre + 240, delta=3)
        lat, lon, _ = rota.ponto_em(2000)                   # andou metade do que faltava: metade do atraso
        e = nav.atualizar(lat, lon, 30.0, 12.0)
        self.assertAlmostEqual(e["restante_s"], rota.tempo_s * 1000 / 3000 + 120, delta=4)
        nav.trocar_rota(rota_reta(1000, tempo_s=200))
        self.assertIsNone(nav.vivo)

    def test_rotular_deixa_a_rota_da_tomtom_no_fim(self):
        a, b = rota_reta(3000, tempo_s=600), rota_reta(3000, tempo_s=300)
        b.perfil, b.nome_perfil, b.tempo_com_transito = "transito", "Pelo trânsito de agora", True
        lista = rotas.rotular([b, a])
        self.assertEqual([r.nome_perfil for r in lista], ["Mais rápida", "Pelo trânsito de agora"])


if __name__ == "__main__":
    unittest.main()
