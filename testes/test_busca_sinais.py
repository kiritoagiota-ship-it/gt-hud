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


class TestePlusCodeELinkSemCoordenadas(unittest.TestCase):
    def test_plus_code_ida_e_volta(self):
        import pluscode
        from rota import distancia_m
        codigo = pluscode.codificar(-16.6799, -49.2550)
        self.assertEqual(codigo, "58MG8PCW+22")
        self.assertLess(distancia_m(pluscode.decodificar(codigo), (-16.6799, -49.2550)), 15)
        # código curto da página da Barbearia Imagem no Google Maps
        lat, lon = pluscode.recuperar("9MJH+9W", *goiania.CENTRO)
        self.assertAlmostEqual(lat, -16.61906, places=4)
        self.assertAlmostEqual(lon, -49.32019, places=4)
        self.assertEqual(pluscode.achar("9MJH+9W St. Morada do Sol, Goiânia"), "9MJH+9W")
        self.assertIsNone(pluscode.achar("Rua 5, 120"))

    def test_plus_code_colado_vira_destino(self):
        lugar = busca.lugar_colado("9MJH+9W St. Morada do Sol, Goiânia")
        self.assertEqual(lugar["nome"], "Plus Code 9MJH+9W")
        self.assertAlmostEqual(lugar["lat"], -16.61906, places=4)

    def test_link_do_app_sem_coordenadas_usa_o_endereco(self):
        # o link curto real (maps.app.goo.gl) leva a uma página assim, sem lat/lon
        final = ("https://www.google.com/maps/place/BARBEARIA+IMAGEM+-+R.+do+Sereno,+quadra+141+-+lote+20"
                 "+-+St.+Morada+do+Sol,+Goi%C3%A2nia+-+GO,+74475-211/data=!4m2!3m1!1s0x935ef4d6d0236577:0x2")
        consultas = []

        def geo(consulta):
            consultas.append(consulta)
            return (-16.6182, -49.3222)
        lugar = busca.lugar_colado("https://maps.app.goo.gl/abc", resolver=lambda u: final, geocodificar=geo)
        self.assertEqual(consultas, ["Rua do Sereno, Setor Morada do Sol, Goiânia"])
        self.assertEqual(lugar["nome"], "BARBEARIA IMAGEM")
        self.assertTrue(lugar["aproximado"])
        self.assertTrue(lugar["endereco"].startswith("Aproximado"))


if __name__ == "__main__":
    unittest.main()


class TesteNomeDoColado(unittest.TestCase):
    """Ponto colado sempre ganha nome: o do link, o do lugar conhecido ali, ou perguntado."""

    def test_codigo_e_coordenada_avisam_que_nao_tem_nome(self):
        self.assertTrue(busca.lugar_colado("9MJH+9W Goiânia")["sem_nome"])
        self.assertTrue(busca.lugar_colado("-16.70123, -49.27012")["sem_nome"])

    def test_link_com_nome_ja_vem_com_nome(self):
        lugar = busca.lugar_colado("https://www.google.com/maps/place/Padaria+Boa/@-16.68,-49.25,17z")
        self.assertEqual(lugar["nome"], "Padaria Boa")
        self.assertNotIn("sem_nome", lugar)

    def test_sugere_o_lugar_conhecido_no_ponto(self):
        achado = busca.buscar("bosque dos buritis")[0]
        self.assertEqual(busca.nome_perto(achado["lat"], achado["lon"], 5), achado["nome"])
        colado = busca.buscar("%.6f, %.6f" % (achado["lat"], achado["lon"]))[0]
        self.assertTrue(colado["sugestao"])

    def test_sem_lugar_conhecido_nao_inventa_nome(self):
        self.assertEqual(busca.nome_perto(-16.84, -49.44, 30), "")
