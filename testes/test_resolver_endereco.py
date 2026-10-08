"""Endereço escrito -> ponto: CEP diz o bairro, e só vale candidato daquele bairro."""
import unittest

import busca

T9 = "Av T9, 4724, quadra 32, lote 07, Goiânia, Brazil 74333-010"
PERTO = (-16.68, -49.25)


def _cand(lat, lon, bairro, exato=False, nome="Avenida T-9"):
    return {"nome": nome, "endereco": bairro, "lat": lat, "lon": lon, "bairro": bairro, "exato": exato}


class TestePartes(unittest.TestCase):
    def test_rua_numero_e_cep(self):
        self.assertEqual(busca.partes_do_endereco(T9), {"rua": "Av T9", "numero": "4724", "cep": "74333010"})
        self.assertEqual(busca.partes_do_endereco("Rua 9, 250 - Setor Oeste, Goiânia - GO, 74110100"),
                         {"rua": "Rua 9", "numero": "250", "cep": "74110100"})
        self.assertEqual(busca.partes_do_endereco("Rua 10, nº 45, Centro"), {"rua": "Rua 10", "numero": "45", "cep": ""})
        self.assertEqual(busca.partes_do_endereco("Praça Cívica"), {"rua": "Praça Cívica", "numero": "", "cep": ""})

    def test_cep(self):
        resposta = {"logradouro": "Avenida T 9", "bairro": "Jardim Planalto", "localidade": "Goiânia"}
        pedidos = []

        def baixar(url, timeout):
            pedidos.append(url)
            return resposta
        self.assertEqual(busca.consultar_cep("74333010", baixar),
                         {"rua": "Avenida T 9", "bairro": "Jardim Planalto", "cidade": "Goiânia"})
        self.assertEqual(pedidos, ["https://viacep.com.br/ws/74333010/json/"])
        self.assertIsNone(busca.consultar_cep("74333010", lambda u, t: {"erro": True}))
        self.assertIsNone(busca.consultar_cep("123", baixar))


class TesteResolver(unittest.TestCase):
    CEP = staticmethod(lambda cep: {"rua": "Avenida T 9", "bairro": "Jardim Planalto", "cidade": "Goiânia"})

    def test_tomtom_acha_o_numero_no_bairro_do_cep(self):
        consultas = []

        def enderecos(consulta, perto, chave):
            consultas.append(consulta)
            return [_cand(-16.6978, -49.2664, "Setor Marista", exato=True),          # outro bairro: não serve
                    _cand(-16.7105, -49.2970, "Jardim Planalto", exato=True, nome="Avenida T-9, 4724")]
        r = busca.resolver_endereco(T9, PERTO, "CHAVE", cep_de=self.CEP, enderecos=enderecos)
        self.assertEqual(consultas, ["Avenida T 9 4724, Jardim Planalto, Goiânia"])      # o nome oficial + o bairro
        self.assertEqual((r["lugar"]["lat"], r["lugar"]["nome"], r["lugar"]["endereco"], r["certo"]),
                         (-16.7105, "Av T9, 4724", "Jardim Planalto", True))

    def test_sem_o_numero_fica_a_rua_no_bairro_e_avisa_que_nao_e_certo(self):
        def enderecos(consulta, perto, chave):
            return [_cand(-16.7105, -49.2970, "Jardim Planalto")]                     # só a rua
        r = busca.resolver_endereco(T9, PERTO, "CHAVE", cep_de=self.CEP, enderecos=enderecos)
        self.assertEqual((r["lugar"]["lat"], r["certo"]), (-16.7105, False))

    def test_sem_tomtom_o_mapa_aberto_procura_a_rua_sem_o_numero_no_bairro(self):
        import chaves
        original, chaves._cache = chaves._cache, {}
        consultas = []

        def photon(consulta, perto):
            consultas.append(consulta)
            return [{"nome": "Avenida T-9", "endereco": "Avenida T-9, Setor Bueno, Goiânia", "lat": -16.70, "lon": -49.27},
                    {"nome": "Avenida T-9", "endereco": "Avenida T-9, Jardim Planalto, Goiânia", "lat": -16.711, "lon": -49.30}]
        try:
            r = busca.resolver_endereco(T9, PERTO, None, cep_de=self.CEP, photon=photon)
        finally:
            chaves._cache = original
        self.assertEqual(consultas, ["Avenida T 9, Jardim Planalto, Goiânia"])
        self.assertEqual((r["lugar"]["lat"], r["certo"]), (-16.711, False))

    def test_nada_no_bairro_do_cep_nao_inventa(self):
        def enderecos(consulta, perto, chave):
            return [_cand(-16.6978, -49.2664, "Setor Marista", exato=True)]
        r = busca.resolver_endereco(T9, PERTO, "CHAVE", cep_de=self.CEP, enderecos=enderecos, photon=lambda c, p: [])
        self.assertIsNone(r)                                                        # o app abre a busca

    def test_cep_de_outra_cidade(self):
        fora = lambda cep: {"rua": "Avenida Paulista", "bairro": "Bela Vista", "cidade": "São Paulo"}   # noqa: E731
        self.assertIsNone(busca.resolver_endereco("Av. Paulista, 1000, 01310-100", PERTO, "CHAVE", cep_de=fora,
                                                  enderecos=lambda *a: [_cand(-16.7, -49.3, "Bela Vista")]))

    def test_sem_cep_usa_o_que_achar_e_o_cep_fora_do_ar_nao_derruba(self):
        def cep_quebrado(cep):
            raise OSError("sem internet")
        r = busca.resolver_endereco("Rua 9, 250, Goiânia, 74110-100", PERTO, "CHAVE", cep_de=cep_quebrado,
                                    enderecos=lambda *a: [_cand(-16.68, -49.27, "Setor Oeste", exato=True)])
        self.assertEqual((r["lugar"]["nome"], r["certo"], r["bairro"]), ("Rua 9, 250", True, ""))


if __name__ == "__main__":
    unittest.main()
