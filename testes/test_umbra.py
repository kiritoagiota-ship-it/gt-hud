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
            # o "não" desfaz o pedido (até a 1.0.89, "não vai" iniciava a rota)
            "não vai": ("negou", None),
            "pode não": ("negou", None),
            "vai pra casa não": ("negou", None),
            "não quero ir pra casa": ("negou", None),
            "não cancela": ("negou", None),
            "não, me leva pra casa": ("casa", None),
            # qualquer lugar pelo nome
            "me leva pro Shopping Flamboyant": ("lugar", "shopping flamboyant"),
            "bora pra padaria do zé": ("lugar", "padaria do ze"),
            "me leva no flamboyant por favor": ("lugar", "flamboyant"),
            "me leva pra farmácia": ("perto", "Farmácia"),
            "vamos pro meu trabalho": ("trabalho", None),
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
        self.acordou = 0

    def mostrar(self, modo):
        self.modo = modo

    def acordar(self):
        self.acordou += 1

    def esconder(self):
        self.modo = None

    def definir_estado(self, nome):
        self.estados.append(nome)

    def legenda(self, ouvido=None, fala=None):
        self.legendas.append((ouvido, fala))

    def olhar_para(self, lado):
        self.lado = lado


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
        self.assertTrue(self.voz.ditas[0].startswith("umbra_oi_"))
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
        self.andar(32)                                        # (com a paciência: dois silêncios LONGOS)
        self.assertTrue(any(d.startswith("umbra_silencio") for d in self.voz.ditas))
        self.assertTrue(self.voz.ditas[-1].startswith("umbra_tchau"))
        self.assertIsNone(self.rosto.modo)

    def test_paciencia_nao_acha_que_voce_sumiu_em_2_segundos(self):
        # relato do dono (15/10/2026): "não passa nem 2 segundos e ele acha que eu tô inativo"
        for _ in range(6):
            self.escuta.dizer("")                             # o reconhecedor volta vazio, rápido, várias vezes
        self.u.chamar(agora=self.t)
        self.andar(1.5 + umbra.PACIENCIA_S - 1.0)             # cumprimento + quase toda a paciência
        self.assertFalse(any(d.startswith(("umbra_silencio", "umbra_tchau")) for d in self.voz.ditas),
                         self.voz.ditas)
        self.assertEqual(self.u.estado, umbra.OUVINDO)        # segue ouvindo, calado
        self.escuta.dizer("me leva pra casa")                 # e ainda entende quando você fala
        self.andar(1)
        self.assertIn("umbra_casa", self.voz.ditas)

    def test_age_antes_do_fim_da_frase(self):
        self.u.chamar(agora=self.t)
        self.andar(1.6)                                       # cumprimentou: ouvindo
        self.assertEqual(self.u.estado, umbra.OUVINDO)
        self.escuta.parcial = lambda: "me leva pra casa"      # o reconhecedor ainda não terminou
        self.andar(0.3)
        self.assertNotIn("umbra_casa", self.voz.ditas)        # (parado há pouco: pode vir mais)
        self.assertTrue(any(o == "me leva pra casa" for o, _ in self.rosto.legendas))   # já aparece na tela
        self.andar(0.5)
        self.assertIn("umbra_casa", self.voz.ditas)           # parado 0,5 s: já age, sem o resultado final

    def test_lugar_pelo_nome_espera_a_frase_inteira(self):
        self.u.chamar(agora=self.t)
        self.andar(1.6)
        self.escuta.parcial = lambda: "me leva pro shopping"  # um lugar pelo nome: pode estar crescendo
        self.andar(2)
        self.assertNotIn(("procurar",), self.app.feito)

    def test_acorda_ao_ser_chamado(self):
        self.u.chamar(agora=self.t)
        self.assertEqual(self.rosto.acordou, 1)

    def test_irritado_quando_nao_entende(self):
        self.escuta.dizer("qual é a capital da frança")
        self.u.chamar(agora=self.t)
        self.andar(3)
        self.assertIn("irritado", self.rosto.estados)

    def test_pensando_enquanto_a_rota_vem(self):
        self.escuta.dizer("me leva pra casa")
        self.u.chamar(agora=self.t)
        self.andar(3)
        self.assertEqual(self.u.estado, umbra.ESPERANDO_ROTA)
        self.assertEqual(self.rosto.estados[-1], "pensando")

    def test_nao_entendeu_pede_de_novo(self):
        self.escuta.dizer("qual é a capital da frança")
        self.escuta.dizer("valeu")
        self.u.chamar(agora=self.t)
        self.andar(8)
        self.assertTrue(any(d.startswith("umbra_nao_entendi") for d in self.voz.ditas))
        self.assertTrue(self.voz.ditas[-1].startswith("umbra_valeu"))

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
        self.assertTrue(self.voz.ditas[-1].startswith("umbra_cancelada"))

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

    def test_chamar_pelo_nome_de_novo_depois_de_sumir(self):
        # relato do dono (14/10/2026): chamou, ele respondeu, sumiu sozinho e não voltou mais
        self.u.microfone = True
        for _ in range(3):
            self.escuta.dizer("umbra")
            self.escuta.dizer("")
            self.escuta.dizer("")
            self.andar(4)
            self.assertIn(self.rosto.modo, ("grande",))
            self.andar(32)                                     # silêncio duas vezes (longos): ele vai embora
            self.assertIsNone(self.rosto.modo)

    def test_nome_no_meio_da_fala(self):
        self.u.microfone = True
        self.escuta.parcial = lambda: "ei umbra"               # o parcial já tem o nome; a escuta segue
        self.andar(3.3)
        self.assertIsNone(self.rosto.modo)                     # ainda esperando os 3 s parado
        self.andar(0.7)
        self.assertEqual(self.rosto.modo, "grande")

    def test_nome_com_pedido_espera_a_frase_inteira(self):
        self.u.microfone = True
        self.escuta.parcial = lambda: "umbra me leva"           # veio mais coisa: espera o resultado final
        self.andar(4.5)
        self.assertIsNone(self.rosto.modo)

    def test_gps_oscilando_parado_nao_desliga_a_escuta(self):
        self.u.microfone = True
        self.andar(3.2)
        self.assertEqual(self.u.estado, umbra.VIGIA)
        self.app.vel = 5.0                                     # GPS parado oscilando
        self.andar(1)
        self.assertEqual(self.u.estado, umbra.VIGIA)
        self.app.vel = 15.0                                    # andando de verdade
        self.andar(0.3)
        self.assertEqual(self.u.estado, umbra.OCULTO)

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

    def test_lugar_pelo_nome(self):
        self.escuta.dizer("me leva pro shopping flamboyant")
        self.u.chamar(agora=self.t)
        self.andar(2.5)
        self.assertIn(("procurar",), self.app.feito)
        self.assertIn("umbra_procurando", self.voz.ditas)
        self.assertIn("farejando", self.rosto.estados)         # fareja falando...
        self.assertEqual(self.rosto.estados[-1], "pensando")   # ...e pensa até a resposta chegar
        self.app._resposta([{"nome": "Shopping Flamboyant", "endereco": "Av. Jamel Cecílio", "lat": -16.71,
                             "lon": -49.24}])
        self.assertIn(("destino", "Shopping Flamboyant"), self.app.feito)
        self.assertTrue(any(f and "Jamel" in f for _, f in self.rosto.legendas))
        self.escuta.dizer("bora")
        self.andar(2.5)
        self.assertIn("umbra_lugar_achado", self.voz.ditas)
        self.assertEqual(self.voz.ditas[-1], "rota_calculada")

    def test_lugar_nao_achado(self):
        self.escuta.dizer("me leva pro lugar que nao existe")
        self.u.chamar(agora=self.t)
        self.andar(2.5)
        self.app._resposta([])
        self.assertEqual(self.voz.ditas[-1], "umbra_nao_achou")
        self.assertNotIn(("destino",), [f[:1] for f in self.app.feito])
        self.andar(3)
        self.assertIsNone(self.rosto.modo)

    def test_resposta_curta_vira_busca_e_sem_resultado_nao_entendeu(self):
        self.escuta.dizer("flamboyant")
        self.u.chamar(agora=self.t)
        self.andar(2.5)
        self.assertIn(("procurar",), self.app.feito)
        self.escuta.dizer("valeu")
        self.app._resposta([])
        self.assertTrue(self.voz.ditas[-1].startswith("umbra_nao_entendi"))

    def test_nao_na_confirmacao_cancela(self):
        self.escuta.dizer("farmácia mais perto")
        self.u.chamar(agora=self.t)
        self.andar(2.5)
        self.app._resposta([{"nome": "Drogasil", "lat": -16.69, "lon": -49.26}])
        self.escuta.dizer("não vai")
        self.andar(2.5)
        self.assertIn(("cancelar_previa",), self.app.feito)
        self.assertEqual(self.voz.ditas[-1], "umbra_ok_nao")

    def test_cumprimento_nao_repete_seguido(self):
        ditas = []
        for _ in range(12):
            self.u.chamar(agora=self.t)
            ditas.append(self.voz.ditas[-1])
            self.u.fechar()
        self.assertTrue(all(a != b for a, b in zip(ditas, ditas[1:])), ditas)

    def test_andando_aparece_medio(self):
        self.app.vel = 25.0
        self.u.chamar(agora=self.t)
        self.assertEqual(self.rosto.modo, "medio")
        self.assertEqual(self.voz.ditas[-1], "umbra_andando")         # "Olho na pista..."
        self.u.fechar()
        self.app.vel = 0.0
        self.u.chamar(agora=self.t)
        self.assertEqual(self.rosto.modo, "grande")

    def test_aviso_olha_para_a_curva(self):
        self.app.nav = object()
        self.app.estado_nav = {"manobra": {"acao": "levemente_esquerda"}}
        self.voz.falar(["radar"])
        self.assertEqual(self.rosto.lado, -1)
        self.andar(2)
        self.app.estado_nav = {"manobra": {"acao": "direita"}}
        self.voz.falar(["recalculando"])
        self.assertEqual(self.rosto.lado, 1)

    def test_tocar_fora_fecha(self):
        self.u.chamar(agora=self.t)
        self.u.fechar()
        self.assertIsNone(self.rosto.modo)
        self.assertEqual(self.u.estado, umbra.OCULTO)

    # --- consertos da varredura (15/10/2026) ---------------------------------------------
    def test_lugar_achado_fica_na_legenda(self):
        # ele pergunta "É esse aí? Vamos?": o nome e o endereço têm de FICAR na tela (até a 1.0.94
        # a frase apagava na hora)
        self.escuta.dizer("me leva pro shopping flamboyant")
        self.u.chamar(agora=self.t)
        self.andar(2.5)
        self.app._resposta([{"nome": "Shopping Flamboyant", "endereco": "Av. Jamel Cecílio", "lat": -16.71,
                             "lon": -49.24}])
        self.assertEqual(self.rosto.legendas[-1][1], "Shopping Flamboyant\nAv. Jamel Cecílio")

    def test_farmacia_achada_fica_na_legenda(self):
        self.escuta.dizer("farmácia mais perto")
        self.u.chamar(agora=self.t)
        self.andar(2.5)
        self.app._resposta([{"nome": "Drogasil", "endereco": "Rua 9", "lat": -16.69, "lon": -49.26}])
        self.assertEqual(self.rosto.legendas[-1][1], "Drogasil\nRua 9")

    def test_busca_de_conversa_velha_nao_troca_o_destino(self):
        self.escuta.dizer("farmácia mais perto")
        self.u.chamar(agora=self.t)
        self.andar(2.5)
        velha = self.app._resposta
        self.u.fechar(agora=self.t)                    # o dono dispensou ele no meio da procura
        self.andar(1)
        self.escuta.dizer("me leva pra casa")
        self.u.chamar(agora=self.t)
        self.andar(2.5)
        velha([{"nome": "Drogasil", "lat": -16.69, "lon": -49.26}])
        self.assertEqual(self.app.destino["nome"], "Casa")
        self.assertNotIn(("destino", "Drogasil"), self.app.feito)

    def test_minimizado_aviso_nao_mexe_no_rosto(self):
        self.app.nav = object()
        self.u.pausar()                                # app minimizado
        self.voz.falar(["radar"])
        self.assertIsNone(self.rosto.modo)
        self.assertEqual(self.u.estado, umbra.OCULTO)
        self.u.retomar()
        self.voz.falar(["lombada"])
        self.assertEqual(self.rosto.modo, "pequeno")

    def test_preferida_tranquila_espera_ela_chegar(self):
        class Rota:
            def __init__(self, nome):
                self.nome_perfil = nome
        self.app.ajustes["rota_preferida"] = "tranquila"
        self.app.calculando_alternativas = True
        self.escuta.dizer("me leva pra casa")
        self.u.chamar(agora=self.t)
        self.andar(3)
        self.app.rota_previa = Rota("Mais rápida")      # a rápida chega primeiro
        self.andar(4)
        self.assertNotIn(("iniciar",), self.app.feito)  # espera a tranquila
        self.app.rota_previa = Rota("Mais tranquila")   # chegou: sai por ela
        self.app.calculando_alternativas = False
        self.andar(2)
        self.assertIn(("iniciar",), self.app.feito)

    def test_preferida_tranquila_nao_espera_para_sempre(self):
        class Rota:
            nome_perfil = "Mais rápida"
        self.app.ajustes["rota_preferida"] = "tranquila"
        self.app.calculando_alternativas = True
        self.escuta.dizer("me leva pra casa")
        self.u.chamar(agora=self.t)
        self.andar(3)
        self.app.rota_previa = Rota()
        self.andar(umbra.ESPERA_TRANQUILA_MAX_S + 1)
        self.assertIn(("iniciar",), self.app.feito)

    def test_dispensar_cala_a_frase(self):
        self.u.chamar(agora=self.t)                    # cumprimentando
        self.u.fechar(calar=True)
        self.assertEqual(self.voz.caladas, 1)

    def test_fim_normal_nao_corta_a_fala_da_rota(self):
        self.escuta.dizer("me leva pra casa")
        self.u.chamar(agora=self.t)
        self.andar(3)
        self.app.rota_previa = object()
        self.andar(4)
        self.assertIn(("iniciar",), self.app.feito)
        self.assertEqual(self.voz.caladas, 0)          # ("rota calculada" da navegação segue)

    def test_bateria_fraca_mesmo_limite_do_aviso(self):
        import bateria
        self.assertEqual(umbra.AVISO_BATERIA_M, bateria.AVISO_BAIXA_M)


if __name__ == "__main__":
    unittest.main()
