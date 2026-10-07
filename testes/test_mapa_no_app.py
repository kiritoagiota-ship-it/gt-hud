"""O mapa de Goiânia que vem dentro do app (dados/goiania_mapa.db)."""
import unittest

import mapa_vetor
import mvt
import rede


class TesteMapaNoApp(unittest.TestCase):
    def test_goiania_inteira_esta_no_pacote(self):
        todos = mapa_vetor.FonteVetorial.tiles_goiania()
        self.assertEqual(mapa_vetor.partes_no_pacote(), len(todos))
        self.assertEqual([t for t in todos if mapa_vetor.do_pacote(*t) is None], [])

    def test_os_pedacos_abrem(self):
        z14 = mapa_vetor.FonteVetorial.tiles_goiania((14,))
        for z, x, y in z14[::37]:
            camadas = mvt.ler(mapa_vetor.do_pacote(z, x, y), ("transportation", "water", "landuse"))
            self.assertIsInstance(camadas, dict)
        centro = max(z14, key=lambda t: len(mapa_vetor.do_pacote(*t)))     # o pedaço mais cheio: o centro
        self.assertGreater(len(mvt.ler(mapa_vetor.do_pacote(*centro), ("transportation",))["transportation"][1]), 200)

    def test_fora_de_goiania_nao_esta(self):
        self.assertIsNone(mapa_vetor.do_pacote(14, 0, 0))

    def test_ler_um_pedaco_de_goiania_nao_usa_a_internet(self):
        def sem_rede(url, timeout=20):
            raise AssertionError("foi à internet: " + url)
        original = rede.baixar
        rede.baixar = sem_rede
        try:
            z, x, y = mapa_vetor.FonteVetorial.tiles_goiania((13,))[40]
            fonte = mapa_vetor.FonteVetorial.__new__(mapa_vetor.FonteVetorial)     # sem threads nem pasta
            self.assertEqual(fonte._ler_ou_baixar(z, x, y), mapa_vetor.do_pacote(z, x, y))
        finally:
            rede.baixar = original


class TestePedacosProntos(unittest.TestCase):
    """O pedaço desenhado uma vez fica guardado: na vez seguinte não é desenhado de novo."""

    CAMADAS = ("landuse", "park", "landcover", "water", "building",
               "transportation", "transportation_name", "place", "poi")

    def _centro(self):
        z14 = mapa_vetor.FonteVetorial.tiles_goiania((14,))
        return max(z14, key=lambda t: len(mapa_vetor.do_pacote(*t)))

    def test_empacotar_e_desempacotar_da_o_mesmo_desenho(self):
        z, x, y = self._centro()
        camadas = mvt.ler(mapa_vetor.do_pacote(z, x, y), self.CAMADAS)
        feito = mapa_vetor.preparar(camadas, 14, x, y, 17, mapa_vetor.origem_padrao(), 2.75, 2.75)
        lido = mapa_vetor.desempacotar(mapa_vetor.empacotar(feito), 17)
        self.assertEqual([(n, l) for n, l in feito["areas"]], [(n, l) for n, l in lido["areas"]])
        self.assertEqual(feito["ruas"], lido["ruas"])                 # geometria E cores (as do tema de agora)
        self.assertEqual(feito["rotulos"], lido["rotulos"])
        self.assertEqual(sorted(feito["grade"]), sorted(lido["grade"]))
        celula = next(iter(lido["grade"].values()))
        self.assertTrue(any(celula[0] is r for r in lido["rotulos"]))  # a grade aponta para os MESMOS nomes

    def test_segunda_vez_vem_do_disco(self):
        import tempfile
        z, x, y = self._centro()
        chave = (14, x, y, 15)                                         # zoom que não vem pronto no app
        with tempfile.TemporaryDirectory() as pasta:
            fonte = mapa_vetor.FonteVetorial.__new__(mapa_vetor.FonteVetorial)   # sem threads
            fonte.pasta = pasta
            fonte._pasta_prontos = pasta + "/prontos"
            fonte.origem, fonte.escala, fonte.densidade = mapa_vetor.origem_padrao(), 2.75, 2.75
            fonte._decodificados = {}
            fonte._trava = __import__("threading").Lock()
            fonte.lidos_do_disco = fonte.lidos_do_app = fonte.preparados_agora = 0
            primeiro = fonte._preparar(chave)
            self.assertEqual((fonte.preparados_agora, fonte.lidos_do_disco), (1, 0))
            segundo = fonte._preparar(chave)
            self.assertEqual((fonte.preparados_agora, fonte.lidos_do_disco), (1, 1))
            self.assertEqual(primeiro["ruas"], segundo["ruas"])
            with open(fonte._caminho_pronto(chave), "wb") as f:        # arquivo estragado: refaz, não quebra
                f.write(b"lixo")
            terceiro = fonte._preparar(chave)
            self.assertEqual(fonte.preparados_agora, 2)
            self.assertEqual(primeiro["ruas"], terceiro["ruas"])

    def test_niveis_de_desenho_sao_so_os_que_vem_prontos(self):
        import widgets.mapa as wm
        for decimo in range(110, 191):
            self.assertIn(wm.nivel_de_desenho(decimo / 10.0), mapa_vetor.ZOOMS_PRONTOS)
        self.assertEqual([wm.nivel_de_desenho(z) for z in (11, 14.4, 15.0, 15.4, 16, 17.4, 18, 19)],
                         [11, 14, 14, 16, 16, 17, 17, 17])


if __name__ == "__main__":
    unittest.main()
