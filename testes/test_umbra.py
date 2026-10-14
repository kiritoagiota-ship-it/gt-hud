"""O Umbra: entender o que foi dito e conduzir a conversa (com voz, ouvido e app de mentira)."""
import random
import unittest

import caminhos  # noqa: F401
import falas
import umbra
from escuta import Escuta


class TesteEntender(unittest.TestCase):
    def test_pedidos(self):
        casos = {
            "me leva pra casa": ("casa", None),
            "Vamos pra CASA!": ("casa", None),
            "quero ir pro trabalho": ("trabalho", None),
            "tem outra rota?": ("rotas", None),
            "mostra outros caminhos": ("rotas", None),
            "como tá a bateria": ("bateria", None),
            "quantos km de carga ainda": ("bateria", None),
            "farmácia mais perto": ("perto", "Farmácia"),
            "tô com fome": ("perto", "Lanche"),
            "acha um mercado": ("perto", "Mercado"),
            "cancela a rota de casa": ("cancelar", None),
            "valeu": ("valeu", None),
            "nada não": ("tchau", None),
            "bora": ("iniciar", None),
            "qual é a capital da frança": ("desconhecido", None),
            "": ("nada_dito", None),
        }
        for texto, esperado in casos.items():
            self.assertEqual(umbra.entender(texto), esperado, texto)

    def test_palavra_inteira(self):
        self.assertEqual(umbra.entender("levar")[0], "desconhecido")     # "lar" dentro de "levar" não é casa
        self.assertEqual(umbra.entender("saída")[0], "desconhecido")     # "sai" dentro de "saída" não é tchau

    def test_chamado(self):
        self.assertEqual(umbra.chamado(["Umbra"]), (True, ""))
        self.assertEqual(umbra.chamado(["ei Umbra, me leva pra casa"]), (True, "me leva pra casa"))
        self.assertEqual(umbra.chamado(["sombra", "hum bra"]), (True, ""))   # a 2ª alternativa vale
        self.assertEqual(umbra.chamado(["que horas são"]), (False, ""))
        self.assertFalse(umbra.chamado(["penumbra"])[0])

    def test_alternativas(self):
        (r, d), texto = umbra.entender_alternativas(["me leva pra cara", "me leva pra casa"])
        self.assertEqual((r, texto), ("casa", "me leva pra casa"))

    def test_falas_existem(self):
        for chave in falas.UMBRA:
            self.assertIn(chave, falas.FALAS)
            self.assertIn(chave, falas.GRAVADAS)


# ---------------------------------------------------------------- peças de mentira
class VozFalsa:
    def __init__(self):
        self.ditas = []
        self.ate = 0.0
        self.agora = 0.0
        self.ao_tocar = None
        self.caladas = 0

    def falar(self, pedacos, prioridade=1, texto=None):
        self.ditas.append(pedacos[0])
        self.ate = self.agora + 1.0             # cada fala dura 1 s
        if self.ao_tocar:
            self.ao_tocar(pedacos)

    def ocupada(self):
        return self.agora < self.ate

    def calar(self):
        self.caladas += 1
        self.ate = 0.0


class RostoFalso:
    def __init__(self):
        self.modo = None
        self.estados = []
        self.legendas = []

    def mostrar(self, modo):
        self.modo = modo

    def esconder(self):
        self.modo = None

    def definir_estado(self, nome):
        self.estados.append(nome)

    def legenda(self, ouvido=None, fala=None):
        self.legendas.append((ouvido, fala))


class BateriaFalsa:
    def __init__(self, resta=None, barras=5):
        self.carga = {"m": 1000.0} if resta is not None else None
        self._resta, self.barras = resta, barras

    def restante_m(self):
        return self._resta

    def texto_previsao(self):
        return "Restam uns %d km" % round((self._resta or 0) / 1000.0)


class AppFalso:
    def __init__(self):
        self.ajustes = {"atalhos": {"casa": {"nome": "Casa", "lat": -16.7, "lon": -49.3}},
                        "umbra_escuta": True}
        self.nav = None
        self.destino = None
        self.rota_previa = None
        self.posicao = (-16.68, -49.25)
        self.vel = 0.0
        self.bateria = BateriaFalsa(resta=20000)
        self.feito = []

    def velocidade_agora(self):
        return self.vel

    def escolher_destino(self, lugar):
        self.destino = lugar
        self.feito.append(("destino", lugar["nome"]))

    def iniciar_navegacao(self):
        self.nav = object()
        self.feito.append(("iniciar",))

    def encerrar_navegacao(self, chegou=False):
        self.nav = None
        self.feito.append(("encerrar",))

    def cancelar_previa(self):
        self.destino = self.rota_previa = None
        self.feito.append(("cancelar_previa",))

    def calcular_rotas_navegando(self):
        self.feito.append(("rotas",))

    def em_segundo_plano(self, tarefa, ok, falhou=None):
        self.feito.append(("procurar",))
        self._resposta = ok


class TesteConversa(unittest.TestCase):
    def setUp(self):
        self.app = AppFalso()
        self.voz = VozFalsa()
        self.escuta = Escuta()            # no PC: o que é "dito" entra por dizer()
        self.rosto = RostoFalso()
        self.u = umbra.Umbra(self.app, self.voz, self.escuta, rosto=self.rosto, sorteio=random.Random(1))
        self.voz.ao_tocar = self.u.ao_falar
        self.t = 100.0

    def andar(self, segundos):
        fim = self.t + segundos
        while self.t < fim:
            self.t += 0.1
            self.voz.agora = self.t
            self.u.tique(agora=self.t)

    def test_chamar_cumprimenta_e_leva_para_casa(self):
        self.escuta.dizer("me leva pra casa")
        self.u.chamar(agora=self.t)
        self.assertEqual(self.rosto.modo, "grande")
        self.assertIn(self.voz.ditas[0], ("umbra_oi_1", "umbra_oi_2", "umbra_oi_3"))
        self.andar(3)                                         # cumprimentou, ouviu, respondeu
        self.assertEqual(self.voz.ditas[1], "umbra_casa")
        self.assertIn(("destino", "Casa"), self.app.feito)
        self.app.rota_previa = object()                       # a rota chegou
        self.andar(4)
        self.assertIn(("iniciar",), self.app.feito)           # pedido de voz: já sai navegando
        self.assertIsNone(self.rosto.modo)
        self.assertEqual(self.u.estado, umbra.OCULTO)

    def test_sem_casa_salva(self):
        self.app.ajustes["atalhos"] = {}
        self.escuta.dizer("me leva pra casa")
        self.u.chamar(agora=self.t)
        self.andar(3)
        self.assertIn("umbra_sem_casa", self.voz.ditas)
        self.assertNotIn(("destino", "Casa"), self.app.feito)

    def test_silencio_duas_vezes_e_ele_vai_embora(self):
        self.escuta.dizer("")
        self.escuta.dizer("")
        self.u.chamar(agora=self.t)
        self.andar(8)
        self.assertIn("umbra_silencio", self.voz.ditas)
        self.assertEqual(self.voz.ditas[-1], "umbra_tchau")
        self.assertIsNone(self.rosto.modo)

    def test_nao_entendeu_pede_de_novo(self):
        self.escuta.dizer("qual é a capital da frança")
        self.escuta.dizer("valeu")
        self.u.chamar(agora=self.t)
        self.andar(8)
        self.assertTrue(any(d.startswith("umbra_nao_entendi") for d in self.voz.ditas))
        self.assertEqual(self.voz.ditas[-1], "umbra_valeu")

    def test_bateria(self):
        self.escuta.dizer("como tá a bateria")
        self.u.chamar(agora=self.t)
        self.andar(4)
        self.assertIn("umbra_bateria_ok", self.voz.ditas)
        self.app.bateria = BateriaFalsa(resta=3000)
        self.escuta.dizer("bateria")
        self.u.chamar(agora=self.t)
        self.andar(4)
        self.assertIn("umbra_bateria_fraca", self.voz.ditas)

    def test_bateria_sem_carga_marcada_so_escreve(self):
        self.app.bateria = BateriaFalsa(resta=None)
        self.escuta.dizer("bateria")
        self.u.chamar(agora=self.t)
        self.andar(2.5)
        self.assertFalse(any(d.startswith("umbra_bateria") for d in self.voz.ditas))
        self.assertTrue(any(f and "Carreguei" in f for _, f in self.rosto.legendas))
        self.andar(5)
        self.assertIsNone(self.rosto.modo)

    def test_perto_pergunta_e_confirma(self):
        self.escuta.dizer("farmácia mais perto")
        self.u.chamar(agora=self.t)
        self.andar(2.5)
        self.assertIn("umbra_farejando", self.voz.ditas)
        self.assertIn(("procurar",), self.app.feito)
        self.app._resposta([{"nome": "Drogasil", "lat": -16.69, "lon": -49.26}])
        self.assertIn(("destino", "Drogasil"), self.app.feito)
        self.assertEqual(self.voz.ditas[-1], "umbra_achou")
        self.escuta.dizer("bora")
        self.andar(2.5)
        self.assertEqual(self.voz.ditas[-1], "rota_calculada")
        self.app.rota_previa = object()
        self.andar(3)
        self.assertIn(("iniciar",), self.app.feito)

    def test_cancelar_navegando(self):
        self.app.nav = object()
        self.escuta.dizer("cancela a rota")
        self.u.chamar(agora=self.t)
        self.andar(3)
        self.assertIn(("encerrar",), self.app.feito)
        self.assertEqual(self.voz.ditas[-1], "umbra_cancelada")

    def test_outras_rotas_navegando(self):
        self.app.nav = object()
        self.escuta.dizer("tem outra rota")
        self.u.chamar(agora=self.t)
        self.andar(3)
        self.assertIn(("rotas",), self.app.feito)

    def test_nome_e_pedido_juntos(self):
        self.u.chamar("me leva pra casa", agora=self.t)
        self.assertEqual(self.voz.ditas[0], "umbra_casa")      # sem cumprimento: já faz

    def test_avisos_so_com_rota(self):
        self.voz.falar(["radar"])
        self.assertIsNone(self.rosto.modo)                     # sem rota: não aparece
        self.app.nav = object()
        self.voz.falar(["senhor", "em_200", "radar"])
        self.assertEqual(self.rosto.modo, "pequeno")
        self.assertEqual(self.rosto.estados[-1], "alerta")
        self.andar(2)
        self.assertIsNone(self.rosto.modo)                     # falou e sumiu
        self.voz.falar(["vire_direita"])                       # curva não é aviso dele
        self.assertIsNone(self.rosto.modo)
        self.voz.falar(["chegou"])
        self.assertEqual(self.rosto.estados[-1], "confirmou")

    def test_bateria_fraca_aparece_mesmo_sem_rota(self):
        self.u.aviso_bateria()
        self.assertEqual(self.rosto.modo, "pequeno")

    def test_escuta_o_nome_so_parado(self):
        self.u.microfone = True
        self.app.vel = 20.0
        self.escuta.dizer("umbra")
        self.andar(5)
        self.assertEqual(self.u.estado, umbra.OCULTO)          # andando: não escuta
        self.assertIsNone(self.rosto.modo)
        self.app.vel = 0.0
        self.andar(4)                                          # parado por 3 s: escuta e ouve o nome
        self.assertEqual(self.rosto.modo, "grande")

    def test_sem_microfone_nao_escuta(self):
        self.u.microfone = False
        self.escuta.dizer("umbra")
        self.andar(6)
        self.assertIsNone(self.rosto.modo)

    def test_escuta_desligada_nos_ajustes(self):
        self.u.microfone = True
        self.app.ajustes["umbra_escuta"] = False
        self.escuta.dizer("umbra")
        self.andar(6)
        self.assertIsNone(self.rosto.modo)

    def test_tocar_fora_fecha(self):
        self.u.chamar(agora=self.t)
        self.u.fechar()
        self.assertIsNone(self.rosto.modo)
        self.assertEqual(self.u.estado, umbra.OCULTO)


if __name__ == "__main__":
    unittest.main()
