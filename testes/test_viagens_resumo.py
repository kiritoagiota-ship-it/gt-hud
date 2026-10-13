"""O resumo da tela Viagens (semana, mês, total) e a lista separada por dia."""
import time
import unittest

import caminhos  # noqa: F401
from telas import viagens


def em(ano, mes, dia, hora=12, minuto=0):
    return time.mktime((ano, mes, dia, hora, minuto, 0, 0, 0, -1))


AGORA = em(2026, 10, 14, 15)          # quarta-feira


def v(vid, quando, metros, destino=""):
    return {"id": vid, "inicio": quando, "distancia_m": metros, "duracao_s": 600, "vel_max_kmh": 40, "destino": destino}


class TesteResumo(unittest.TestCase):
    VIAGENS = [v(6, em(2026, 10, 14, 9), 4000, "Barbearia"), v(5, em(2026, 10, 14, 7, 30), 2500),
               v(4, em(2026, 10, 13, 18), 6000), v(3, em(2026, 10, 12, 0, 5), 1000),      # segunda, logo depois da meia-noite
               v(2, em(2026, 10, 11, 23, 50), 9000),                                      # domingo: semana passada
               v(1, em(2026, 9, 30, 12), 20000), v(0, em(2025, 12, 31, 12), 700)]

    def test_semana_mes_e_total(self):
        r = viagens.resumo(self.VIAGENS, AGORA)
        self.assertEqual(r["semana"], (13500.0, 4))       # de segunda para cá
        self.assertEqual(r["mes"], (22500.0, 5))          # outubro
        self.assertEqual(r["total"], (43200.0, 7))
        self.assertEqual(viagens.resumo([], AGORA)["total"], (0.0, 0))

    def test_nome_do_dia(self):
        self.assertEqual(viagens.nome_do_dia(em(2026, 10, 14, 0, 1), AGORA), "Hoje")
        self.assertEqual(viagens.nome_do_dia(em(2026, 10, 13, 23, 59), AGORA), "Ontem")
        self.assertEqual(viagens.nome_do_dia(em(2026, 10, 12), AGORA), "seg, 12/10")
        self.assertEqual(viagens.nome_do_dia(em(2025, 12, 31), AGORA), "qua, 31/12/2025")

    def test_lista_separada_por_dia_com_o_total_de_cada_um(self):
        saida = viagens.linhas(self.VIAGENS, AGORA)
        titulos = [x for tipo, x in saida if tipo == "dia"]
        self.assertEqual(titulos[:4], ["Hoje  ·  6,5 km em 2 viagens", "Ontem  ·  6,0 km em 1 viagem",
                                       "seg, 12/10  ·  1,0 km em 1 viagem", "dom, 11/10  ·  9,0 km em 1 viagem"])
        self.assertEqual(saida[0][0], "dia")                                   # o título vem antes das viagens do dia
        self.assertEqual([x["id"] for tipo, x in saida if tipo == "viagem"], [6, 5, 4, 3, 2, 1, 0])
        self.assertEqual(viagens.linhas([], AGORA), [])


if __name__ == "__main__":
    unittest.main()
