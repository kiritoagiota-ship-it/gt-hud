"""Link do Google compartilhado (o ponto do lugar, e o plano B pelo nome e endereço) e o
lado da rua em que o destino fica ao chegar."""
import unittest

import caminhos  # noqa: F401
import busca
import navegacao
from navegacao import lado_do_destino
from rota import Rota

M = 1.0 / 111320.0   # 1 metro em graus de latitude
LAT, LON = -16.6800, -49.2600


def rota_para_o_norte(ultima_acao="chegada"):
    pontos = [(LAT + k * 20 * M, LON) for k in range(11)]          # 200 m para o norte
    return Rota(pontos, [{"acao": "em_frente", "indice": 0}, {"acao": ultima_acao, "indice": 10}], [], 60)


class TesteLadoDoDestino(unittest.TestCase):
    def test_o_servidor_de_rotas_manda(self):
        self.assertEqual(lado_do_destino(rota_para_o_norte("chegada_direita")), "direita")
        self.assertEqual(lado_do_destino(rota_para_o_norte("chegada_esquerda"), (LAT, LON + 1)), "esquerda")

    def test_sem_isso_a_conta_pelo_ponto_do_lugar(self):
        rota = rota_para_o_norte()
        fim = rota.pontos[-1]
        leste, oeste = (fim[0], fim[1] + 25 * M), (fim[0], fim[1] - 25 * M)
        self.assertEqual(lado_do_destino(rota, leste), "direita")    # indo para o norte, o leste é a direita
        self.assertEqual(lado_do_destino(rota, oeste), "esquerda")
        self.assertIsNone(lado_do_destino(rota, (fim[0], fim[1] + 3 * M)))   # na beira da rua: sem lado
        self.assertIsNone(lado_do_destino(rota, None))

    def test_ao_chegar_fala_o_lado(self):
        falou = []
        rota = rota_para_o_norte()
        nav = navegacao.Navegacao(rota, lambda pedacos, prioridade=1, texto=None: falou.append(list(pedacos)))
        fim = rota.pontos[-1]
        nav.alvo = (fim[0], fim[1] - 30 * M)
        nav.atualizar(fim[0] - 5 * M, fim[1], 10.0, 100.0)
        self.assertTrue(nav.chegou)
        self.assertEqual(nav.lado_chegada, "esquerda")
        self.assertEqual(falou[-1], ["senhor", "chegou", "destino_esquerda"])


class TesteCompartilhado(unittest.TestCase):
    def test_o_que_chega_pelo_compartilhar(self):
        texto = "Barbearia Imagem\nhttps://maps.app.goo.gl/AbCdEf123?g_st=aw"
        self.assertEqual(busca.texto_compartilhado(texto), {"link": texto})
        self.assertEqual(busca.texto_compartilhado("Av. T-9, 4724 - Jardim América,  Goiânia"),
                         {"texto": "Av. T-9, 4724 - Jardim América, Goiânia"})
        self.assertIsNone(busca.texto_compartilhado("olha isso https://youtu.be/xyz"))   # link que não é de mapa
        self.assertIsNone(busca.texto_compartilhado("tel:123"))
        self.assertIsNone(busca.texto_compartilhado(""))
        self.assertIsNone(busca.texto_compartilhado(None))

    def test_link_com_o_ponto_do_lugar_e_exato(self):
        final = "https://www.google.com/maps/place/Barbearia+Imagem/@-16.70,-49.30,17z/data=!3m1!4b1!8m2!3d-16.7012345!4d-49.3123456"
        lugar = busca.lugar_colado("Barbearia Imagem\nhttps://maps.app.goo.gl/x", resolver=lambda u: final)
        self.assertEqual((lugar["lat"], lugar["lon"]), (-16.7012345, -49.3123456))   # o pino, não o centro do mapa
        self.assertEqual(lugar["nome"], "Barbearia Imagem")
        self.assertNotIn("aproximado", lugar)


class TesteLinkSemPonto(unittest.TestCase):
    TITULO = "BARBEARIA IMAGEM - R. do Sereno, quadra 141 - lote 20 - St. Morada do Sol, Goiânia - GO, 74475-211"

    def _resolver(self, certo):
        vistos = []

        def resolver(texto, perto, chave):
            vistos.append(texto)
            return {"lugar": {"nome": "R. do Sereno", "endereco": "Setor Morada do Sol", "lat": -16.6400, "lon": -49.3400},
                    "certo": certo, "bairro": "Setor Morada do Sol"}
        return resolver, vistos

    def test_pelo_endereco_com_cep(self):
        resolver, vistos = self._resolver(False)
        lugar = busca._do_titulo(self.TITULO, None, None, resolver_end=resolver, comercios=lambda *a: [])
        self.assertEqual(vistos, ["R. do Sereno, quadra 141, lote 20, St. Morada do Sol, Goiânia, GO, 74475-211"])
        self.assertEqual((lugar["nome"], lugar["lat"]), ("BARBEARIA IMAGEM", -16.64))
        self.assertTrue(lugar["aproximado"])                         # sem o número: avisa que é pela rua
        resolver, _ = self._resolver(True)
        self.assertNotIn("aproximado", busca._do_titulo(self.TITULO, None, None, resolver_end=resolver,
                                                        comercios=lambda *a: []))

    def test_o_comercio_pelo_nome_vale_se_fica_perto_do_endereco(self):
        resolver, _ = self._resolver(False)
        perto = [{"nome": "Barbearia Imagem", "endereco": "Rua do Sereno", "lat": -16.6410, "lon": -49.3405}]
        lugar = busca._do_titulo(self.TITULO, None, "chave", resolver_end=resolver, comercios=lambda *a: perto)
        self.assertEqual((lugar["lat"], lugar["lon"]), (-16.6410, -49.3405))      # o ponto do comércio
        self.assertNotIn("aproximado", lugar)
        longe = [{"nome": "Barbearia Imagem", "endereco": "", "lat": -16.7400, "lon": -49.2000}]   # outra, homônima
        lugar = busca._do_titulo(self.TITULO, None, "chave", resolver_end=resolver, comercios=lambda *a: longe)
        self.assertEqual(lugar["lat"], -16.64)
        outro = [{"nome": "Padaria do Zé", "endereco": "", "lat": -16.6410, "lon": -49.3405}]
        lugar = busca._do_titulo(self.TITULO, None, "chave", resolver_end=resolver, comercios=lambda *a: outro)
        self.assertEqual(lugar["lat"], -16.64)

    def test_sem_nada_devolve_none(self):
        self.assertIsNone(busca._do_titulo(self.TITULO, None, None, resolver_end=lambda *a: None,
                                           comercios=lambda *a: []))


if __name__ == "__main__":
    unittest.main()
