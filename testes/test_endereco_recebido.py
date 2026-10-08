"""Endereço mandado por outro app ("Abrir com" do Android): leitura do geo: e decisão de ir direto."""
import unittest

import busca


class TesteGeo(unittest.TestCase):
    def test_ponto_exato(self):
        self.assertEqual(busca.de_geo("geo:-16.7034,-49.2671"),
                         {"lat": -16.7034, "lon": -49.2671, "nome": "Local recebido"})
        self.assertEqual(busca.de_geo("geo:-16.7034,-49.2671?z=17")["lat"], -16.7034)

    def test_ponto_com_nome(self):
        r = busca.de_geo("geo:0,0?q=-16.7034,-49.2671(Moovie%20Imports)")
        self.assertEqual(r, {"lat": -16.7034, "lon": -49.2671, "nome": "Moovie Imports"})
        r = busca.de_geo("geo:-16.7034,-49.2671?q=Moovie+Imports")       # ponto na frente, nome no q
        self.assertEqual((r["lat"], r["nome"]), (-16.7034, "Moovie Imports"))

    def test_so_o_endereco_escrito(self):
        r = busca.de_geo("geo:0,0?q=Av%20T9%2C%204724%2C%20quadra%2032%2C%20lote%2007%2C%20Goi%C3%A2nia%2C%20Brazil%2074333-010")
        self.assertEqual(r, {"texto": "Av T9, 4724, quadra 32, lote 07, Goiânia, Brazil 74333-010"})
        self.assertEqual(busca.de_geo("google.navigation:q=Av+T9+4724&mode=d"), {"texto": "Av T9 4724"})
        self.assertEqual(busca.de_geo("google.navigation:q=-16.70,-49.26")["lon"], -49.26)

    def test_o_que_nao_e_endereco(self):
        for ruim in ("", None, "geo:", "geo:0,0", "http://exemplo.com", "geo:abc", "geo:999,999", "tel:123"):
            self.assertIsNone(busca.de_geo(ruim), ruim)

    def test_limpa_o_endereco_para_a_busca(self):
        self.assertEqual(busca.texto_de_endereco("Av T9, 4724, quadra 32, lote 07, Goiânia, Brazil 74333-010"),
                         "Av T9, 4724, Goiânia")
        self.assertEqual(busca.texto_de_endereco("Rua 9, 250 - Setor Oeste, Goiânia - GO, 74110-100, Brasil"),
                         "Rua 9, 250 - Setor Oeste, Goiânia - GO")
        self.assertEqual(busca.texto_de_endereco("Praça Cívica"), "Praça Cívica")


class TesteCerteza(unittest.TestCase):
    def _lugar(self, lat, lon, nome="x"):
        return {"nome": nome, "lat": lat, "lon": lon}

    def test_um_resultado_ou_todos_no_mesmo_lugar_vai_direto(self):
        unico = [self._lugar(-16.70, -49.26, "a")]
        self.assertEqual(busca.certeza(unico)["nome"], "a")
        juntos = [self._lugar(-16.7000, -49.2600, "a"), self._lugar(-16.7010, -49.2605), self._lugar(-16.7005, -49.2590)]
        self.assertEqual(busca.certeza(juntos)["nome"], "a")
        # o 4º em diante pode estar longe: só os três primeiros contam
        self.assertIsNotNone(busca.certeza(juntos + [self._lugar(-16.60, -49.20)]))

    def test_lugares_espalhados_ou_nada_pede_escolha(self):
        self.assertIsNone(busca.certeza([]))
        exato = dict(self._lugar(-16.70, -49.26, "Av T9 4724"), exato=True)
        self.assertEqual(busca.certeza([exato, self._lugar(-16.65, -49.30)])["nome"], "Av T9 4724")
        self.assertIsNone(busca.certeza([self._lugar(-16.70, -49.26), self._lugar(-16.65, -49.30)]))


if __name__ == "__main__":
    unittest.main()
