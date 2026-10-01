import json
import unittest

import busca
import goiania
import sinais
from testes.apoio import M_GRAU, rota_reta

CENTRO = (-16.6799, -49.2550)


class TesteBusca(unittest.TestCase):
    """Base offline de Goiânia (dados/goiania_lugares.db) e lugares colados."""

    def test_por_tipo_e_por_nome(self):
        barb = busca._offline("barbearia")
        self.assertGreater(len(barb), 50)
        self.assertTrue(all("barb" in busca.normalizar(l["nome"] + l["endereco"]) for l in barb[:20]))
        bosque = sorted(busca._offline("bosque dos buritis"), key=lambda l: -l["nota"])
        self.assertTrue(bosque[0]["nome"].lower().startswith("bosque dos buritis"), bosque[0])
        self.assertEqual(busca._offline("farmácia")[0]["endereco"].split(",")[0], "Farmácia")

    def test_tudo_em_goiania(self):
        for l in busca._offline("restaurante"):
            self.assertTrue(goiania.dentro(l["lat"], l["lon"]))

    def test_salvo_vem_primeiro(self):
        salvos = [{"nome": "Barbearia do amigo", "endereco": "", "lat": -16.7, "lon": -49.27}]
        r = busca._salvos("amigo barbearia", salvos)
        self.assertEqual(r[0]["nome"], "Barbearia do amigo")
        self.assertEqual(busca._salvos("padaria", salvos), [])

    def test_coordenadas_e_links_do_google_maps(self):
        self.assertEqual(busca.lugar_colado("-16.70123, -49.27012")["lat"], -16.70123)
        longo = ("Barbearia Imagem\nhttps://www.google.com/maps/place/Barbearia+Imagem/"
                 "@-16.7012,-49.2701,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d-16.70125!4d-49.27015")
        lugar = busca.lugar_colado(longo)
        self.assertEqual((lugar["nome"], lugar["lat"], lugar["lon"]), ("Barbearia Imagem", -16.70125, -49.27015))
        self.assertEqual(busca.lugar_colado("https://maps.google.com/?q=-16.6799,-49.2550")["lon"], -49.255)
        curto = busca.lugar_colado("https://maps.app.goo.gl/XyZ", resolver=lambda u: (
            "https://www.google.com/maps/place/Teste/@-16.7,-49.2,17z/data=!3d-16.71!4d-49.21"))
        self.assertEqual((curto["nome"], curto["lat"]), ("Teste", -16.71))
        self.assertIsNone(busca.lugar_colado("barbearia"))
        self.assertIsNone(busca.lugar_colado("Rua 5, 120"))

    def test_link_colado_nao_vai_para_a_internet_na_busca(self):
        r = busca.buscar("-16.70123, -49.27012", CENTRO)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["fonte"], "colado")


class TesteSinais(unittest.TestCase):
    def test_semaforo_no_caminho(self):
        with open(sinais.ARQUIVO, encoding="utf-8") as f:
            lat, lon = json.load(f)["semaforos"][0]
        # rota reta que passa exatamente pelo semáforo (ele fica a 300 m do começo)
        r = rota_reta(600, lat0=lat - 300 / M_GRAU, lon0=lon)
        achados = sinais.ao_longo(r)
        self.assertTrue(any(abs(d - 300) < 20 and t == "semaforo" for d, t in achados), achados)

    def test_na_caixa(self):
        perto = sinais.na_caixa(-16.70, -49.28, -16.66, -49.23)
        self.assertGreater(len(perto), 10)
        self.assertTrue(all(-16.70 <= p[0] <= -16.66 for p in perto))


if __name__ == "__main__":
    unittest.main()
