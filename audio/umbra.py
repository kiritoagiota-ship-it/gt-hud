"""O Umbra: o assistente que aparece quando é chamado.

Pedido do dono (14/10/2026): ele só aparece quando chamado. Chamado (pela voz, dizendo
"Umbra" com a moto parada, ou pelo botão), aparece GRANDE, cumprimenta, escuta o pedido,
responde com humor e age (rota para casa ou trabalho, outras rotas, bateria, o lugar mais
perto, cancelar). Com rota traçada, nos avisos (radar, lombada, semáforo, mudança de rota,
bateria fraca, chegada) ele aparece PEQUENO no canto, fala e some.

Este módulo é o cérebro: entende o que foi dito (entender) e conduz a conversa (Umbra), sem
saber desenhar. O rosto é widgets/rosto_umbra.py; o ouvido, escuta.py; a voz, voz.py.
Tudo anda pelo tique() (o app chama 10 vezes por segundo), com a hora passada de fora:
dá para testar sem relógio de verdade (testes/test_umbra.py).
"""
import random
import time
import unicodedata

import falas

# ---------------------------------------------------------------- entender o que foi dito
# O reconhecedor escreve "Umbra" de vários jeitos (é nome, não palavra comum)
CHAMADOS = ("umbra", "umbral", "um bra", "hum bra", "humbra", "ombra", "lumbra", "numbra", "umbro",
            "zumbra", "humbral", "ambra")

# (intenção, palavras que a indicam); a ordem conta: "cancela a rota de casa" é cancelar
_PALAVRAS = [
    ("cancelar", ("cancela", "cancelar", "encerra", "encerrar", "para a rota", "parar a rota", "desliga a rota",
                  "para de navegar", "sai da rota", "acaba a rota", "termina a rota")),
    ("casa", ("casa", "minha casa", "lar")),
    ("trabalho", ("trabalho", "servico", "firma", "emprego", "serviço")),
    ("rotas", ("outra rota", "outras rotas", "outro caminho", "outros caminhos", "rotas", "caminhos",
               "alternativa", "alternativas", "mais rapido", "rota mais")),
    ("bateria", ("bateria", "carga", "autonomia", "quantos km", "quanto falta de")),
    ("iniciar", ("vamos", "bora", "inicia", "iniciar", "comeca", "começa", "pode ir", "sim", "isso",
                 "pode", "manda", "vai")),
    ("valeu", ("valeu", "obrigado", "obrigada", "brigado", "agradecido", "show")),
    ("tchau", ("nada", "deixa", "esquece", "tchau", "nenhum", "fecha", "sai", "nao", "não", "cancela nada",
               "depois", "ninguem")),
]
# o lugar mais perto: o que a pessoa fala -> o nome da categoria em busca.CATEGORIAS_PERTO
_PERTO = [
    ("Farmácia", ("farmacia", "drogaria", "remedio")),
    ("Mercado", ("mercado", "supermercado", "mercadinho", "atacadao")),
    ("Padaria", ("padaria", "pao")),
    ("Lanche", ("lanche", "lanchonete", "comida", "restaurante", "pizza", "pizzaria", "hamburguer",
                "hamburgueria", "comer", "fome")),
    ("Borracharia", ("borracharia", "bicicletaria", "oficina", "pneu", "conserto")),
    ("Banco", ("banco", "caixa eletronico", "caixa")),
    ("Hospital", ("hospital", "upa", "pronto socorro", "posto de saude", "emergencia")),
]


def normalizar(texto):
    """Minúsculas, sem acento e sem pontuação: "Me leva pra CASA!" -> "me leva pra casa"."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = "".join(c if c.isalnum() else " " for c in t)
    return " ".join(t.split())


def _tem(texto, palavra):
    """A palavra (ou expressão) aparece inteira no texto normalizado."""
    return (" %s " % normalizar(palavra)) in (" %s " % texto)


def chamado(alternativas):
    """O que foi dito chama o Umbra? Devolve (True, o resto da frase depois do nome) ou
    (False, ""). "Umbra, me leva pra casa" -> (True, "me leva pra casa")."""
    for alt in alternativas:
        t = normalizar(alt)
        for nome in CHAMADOS:
            n = normalizar(nome)
            i = (" %s " % t).find(" %s " % n)
            if i >= 0:
                return True, t[i + len(n):].strip()
    return False, ""


def entender(texto):
    """(intenção, dado) do pedido: ("casa", None), ("perto", "Farmácia"), ("desconhecido", None)..."""
    t = normalizar(texto)
    if not t:
        return "nada_dito", None
    for nome, palavras in _PALAVRAS[:1]:                       # cancelar vem antes de tudo
        if any(_tem(t, p) for p in palavras):
            return nome, None
    for categoria, palavras in _PERTO:                        # "farmácia mais perto"
        if any(_tem(t, p) for p in palavras):
            return "perto", categoria
    for nome, palavras in _PALAVRAS[1:]:
        if any(_tem(t, p) for p in palavras):
            return nome, None
    return "desconhecido", None


def entender_alternativas(alternativas):
    """A primeira alternativa do reconhecedor que dá uma intenção conhecida."""
    primeira = None
    for alt in alternativas:
        r = entender(alt)
        if primeira is None:
            primeira = r
        if r[0] not in ("desconhecido", "nada_dito"):
            return r, alt
    return (primeira or ("nada_dito", None)), (alternativas[0] if alternativas else "")


# ---------------------------------------------------------------- a conversa
OCULTO, SAUDANDO, OUVINDO, RESPONDENDO, ESPERANDO_ROTA, AVISO, VIGIA = (
    "oculto", "saudando", "ouvindo", "respondendo", "esperando_rota", "aviso", "vigia")

# os avisos da navegação que fazem o Umbra pequeno aparecer (escolhidos pelo dono)
AVISOS_PERIGO = {"radar", "lombada", "semaforo"}
AVISOS_ROTA = {"recalculando", "rota_trocada", "caminho_melhor", "sem_internet", "gps_perdido", "gps_ok",
               "sem_rota"}
AVISOS_CHEGADA = {"chegou"}

PARADO_KMH = 3.0            # abaixo disso (por PARADO_S) a moto está parada: ele escuta o nome
PARADO_S = 3.0
OUVIR_MAX_S = 12.0          # uma escuta que não termina sozinha
ESPERA_ROTA_MAX_S = 30.0
INICIAR_DEPOIS_S = 1.2      # a rota apareceu: um instante para ver antes de começar
FOLGA_FALA_S = 0.5          # depois de pedir uma fala, o tempo para ela começar
VIGIA_PAUSA_S = 0.4         # entre uma escuta do nome e a próxima
VIGIA_PAUSA_ERRO_S = 6.0    # o reconhecedor falhou (sem internet, ocupado): espera mais
P_UMBRA = 3                 # prioridade das falas dele (passa na frente)


class Umbra:
    def __init__(self, app, voz, escuta, rosto=None, sorteio=None):
        self.app = app
        self.voz = voz
        self.escuta = escuta
        self._rosto = rosto                 # o rosto (ou uma função que o devolve: a tela do mapa)
        self.sorteio = sorteio or random.Random()
        self.estado = OCULTO
        self.pausado = False                # app minimizado: não escuta
        self.microfone = False              # permissão do microfone (o app avisa)
        self._t = 0.0                       # hora do último tique
        self._desde = 0.0                   # hora em que entrou no estado de agora
        self._depois = None                 # depois da fala: "ouvir", "sair", "rota", "confirmar"
        self._silencios = 0
        self._sem_entender = 0
        self._confirmando = False           # perguntou "Vamos?": a resposta é sim ou não
        self._parado_desde = None
        self._vigia_volta = 0.0             # hora em que a escuta do nome pode recomeçar
        self._buscando = False
        self.ultimo_pedido = None           # (para os testes e o diagnóstico) a última intenção

    # --- o rosto -----------------------------------------------------------------
    def rosto(self):
        r = self._rosto
        try:
            return r() if callable(r) and not hasattr(r, "mostrar") else r
        except Exception:
            return None

    def _rosto_faz(self, metodo, *args):
        r = self.rosto()
        if r is not None:
            try:
                getattr(r, metodo)(*args)
            except Exception as e:
                print("[umbra] rosto:", e)

    # --- falar -------------------------------------------------------------------
    def _falar(self, chave, depois, agora, estado_rosto="falando"):
        self.voz.falar([chave], P_UMBRA)
        self.estado = RESPONDENDO if self.estado not in (SAUDANDO,) else SAUDANDO
        self._depois = depois
        self._desde = agora
        self._rosto_faz("definir_estado", estado_rosto)
        self._rosto_faz("legenda", None, falas.GRAVADAS.get(chave, ""))

    def _sorteia(self, *chaves):
        return chaves[self.sorteio.randrange(len(chaves))]

    # --- chamar (botão ou nome) ----------------------------------------------------
    @property
    def conversando(self):
        return self.estado in (SAUDANDO, OUVINDO, RESPONDENDO, ESPERANDO_ROTA)

    def chamar(self, resto="", agora=None):
        agora = self._t if agora is None else agora
        if self.conversando:
            return
        self.escuta.parar()
        self._silencios = self._sem_entender = 0
        self._confirmando = False
        self._rosto_faz("mostrar", "grande")
        self._rosto_faz("legenda", "", "")
        if resto:
            self._rosto_faz("legenda", resto, "")
            self.estado = OUVINDO
            self._desde = agora
            self._processar([resto], agora)
            return
        self.estado = SAUDANDO
        self._falar(self._sorteia("umbra_oi_1", "umbra_oi_2", "umbra_oi_3"), "ouvir", agora)

    def fechar(self, agora=None):
        """Some (tocou fora dele, ou terminou)."""
        self.escuta.parar()
        self.estado = OCULTO
        self._depois = None
        self._confirmando = False
        self._rosto_faz("esconder")

    # --- os avisos da navegação: o Umbra pequeno -------------------------------------
    def ao_falar(self, pedacos):
        """A voz começou uma fala (voz.ao_tocar). Se for um dos avisos escolhidos, o Umbra
        pequeno aparece enquanto ela dura."""
        if self.conversando or not pedacos:
            return
        chaves = set(pedacos)
        navegando = getattr(self.app, "nav", None) is not None
        if "umbra_bateria_fraca" in chaves:
            humor = "alerta"
        elif chaves & AVISOS_PERIGO and navegando:
            humor = "alerta"
        elif chaves & AVISOS_ROTA and navegando:
            humor = "falando"
        elif chaves & AVISOS_CHEGADA:
            humor = "confirmou"
        else:
            return
        if self.estado == VIGIA:
            self.escuta.parar()
        self.estado = AVISO
        self._desde = self._t
        self._rosto_faz("mostrar", "pequeno")
        self._rosto_faz("definir_estado", humor)

    def aviso_bateria(self):
        """Bateria da moto no fim (main.conferir_bateria_baixa): ele avisa, pequeno."""
        if not self.conversando:
            self.voz.falar(["umbra_bateria_fraca"], P_UMBRA)

    # --- o relógio ----------------------------------------------------------------
    def tique(self, dt=None, agora=None):
        agora = time.monotonic() if agora is None else agora
        self._t = agora
        try:
            self._tique(agora)
        except Exception as e:      # o assistente nunca derruba o app
            print("[umbra]", type(e).__name__, e)
            self.estado = OCULTO
            self._rosto_faz("esconder")

    def _tique(self, agora):
        e = self.estado
        if e in (SAUDANDO, RESPONDENDO):
            if agora - self._desde > FOLGA_FALA_S and not self.voz.ocupada():
                self._fim_da_fala(agora)
        elif e == OUVINDO:
            self._ouvindo(agora)
        elif e == ESPERANDO_ROTA:
            self._esperando_rota(agora)
        elif e == AVISO:
            if agora - self._desde > FOLGA_FALA_S and not self.voz.ocupada():
                self.estado = OCULTO
                self._rosto_faz("esconder")
        else:
            self._vigiar(agora)

    def _fim_da_fala(self, agora):
        depois, self._depois = self._depois, None
        if depois == "esperar" and self._buscando:      # ainda procurando o lugar mais perto
            self._depois = "esperar"
            self._desde = agora
            return
        if depois == "ouvir":
            self._ouvir(agora)
        elif depois == "rota":
            self.estado = ESPERANDO_ROTA
            self._desde = agora
            self._rosto_faz("definir_estado", "ouvindo")
        else:
            self.fechar(agora)

    def _ouvir(self, agora):
        self.estado = OUVINDO
        self._desde = agora
        self._rosto_faz("definir_estado", "ouvindo")
        self.escuta.ouvir(1.2)

    def _ouvindo(self, agora):
        sit = self.escuta.situacao()
        if sit == "entendeu":
            alternativas = self.escuta.alternativas()
            self._rosto_faz("legenda", alternativas[0] if alternativas else "", "")
            self._processar(alternativas, agora)
        elif sit in ("nada", "parada") and agora - self._desde > 0.3 or agora - self._desde > OUVIR_MAX_S:
            self.escuta.parar()
            self._silencios += 1
            if self._silencios == 1:
                self._falar("umbra_silencio", "ouvir", agora, "confuso")
            else:
                self._falar("umbra_tchau", "sair", agora)
        elif sit == "sem":
            self._rosto_faz("legenda", None, "O celular não tem reconhecimento de voz.")
            self._falar("umbra_tchau", "sair", agora)

    # --- o que fazer com o pedido ------------------------------------------------------
    def _processar(self, alternativas, agora):
        (intencao, dado), _texto = entender_alternativas(alternativas)
        self.ultimo_pedido = (intencao, dado)
        app = self.app
        if self._confirmando:                      # perguntou "Vamos?"
            self._confirmando = False
            if intencao == "iniciar":
                self._falar("rota_calculada", "rota", agora, "confirmou")
                return
            if intencao in ("tchau", "cancelar"):
                if getattr(app, "rota_previa", None) is not None and app.nav is None:
                    app.cancelar_previa()
                self._falar("umbra_tchau", "sair", agora)
                return
        if intencao == "nada_dito":
            self._silencios += 1
            self._falar("umbra_silencio" if self._silencios == 1 else "umbra_tchau",
                        "ouvir" if self._silencios == 1 else "sair", agora, "confuso")
        elif intencao in ("casa", "trabalho"):
            lugar = (app.ajustes["atalhos"] or {}).get(intencao)
            if not lugar:
                self._falar("umbra_sem_casa" if intencao == "casa" else "umbra_sem_trabalho", "sair", agora, "confuso")
                return
            self._ir_para(lugar)
            self._falar("umbra_casa" if intencao == "casa" else "umbra_trabalho", "rota", agora, "confirmou")
        elif intencao == "rotas":
            if app.nav is not None:
                app.calcular_rotas_navegando()
                self._falar("umbra_rotas", "sair", agora, "confirmou")
            elif getattr(app, "rota_previa", None) is not None:
                self._falar("umbra_rotas", "sair", agora, "confirmou")   # a prévia já mostra todas
            else:
                self._falar("umbra_oi_2", "ouvir", agora)                # rotas para onde?
        elif intencao == "bateria":
            self._bateria(agora)
        elif intencao == "perto":
            self._perto(dado, agora)
        elif intencao == "cancelar":
            if app.nav is not None:
                app.encerrar_navegacao()
                self.voz.calar()                       # (no lugar do "navegação encerrada")
            elif getattr(app, "rota_previa", None) is not None or getattr(app, "destino", None) is not None:
                app.cancelar_previa()
            self._falar("umbra_cancelada", "sair", agora, "confirmou")
        elif intencao == "iniciar":
            if getattr(app, "rota_previa", None) is not None and app.nav is None:
                self._falar("rota_calculada", "rota", agora, "confirmou")
            else:
                self._falar("umbra_oi_2", "ouvir", agora)
        elif intencao == "valeu":
            self._falar("umbra_valeu", "sair", agora, "confirmou")
        elif intencao == "tchau":
            self._falar("umbra_tchau", "sair", agora)
        else:
            self._sem_entender += 1
            if self._sem_entender <= 2:
                self._falar(self._sorteia("umbra_nao_entendi_1", "umbra_nao_entendi_2"), "ouvir", agora, "confuso")
            else:
                self._falar("umbra_tchau", "sair", agora, "confuso")

    def _ir_para(self, lugar):
        app = self.app
        if app.nav is not None:
            app.encerrar_navegacao()
            self.voz.calar()
        app.escolher_destino(lugar)

    def _mostrar_e_sair(self, texto, agora, segundos=4.0):
        """Sem frase gravada para isso: só o texto embaixo dele, e some depois de uns segundos."""
        self._rosto_faz("legenda", None, texto)
        self._rosto_faz("definir_estado", "confuso")
        self.estado = RESPONDENDO
        self._depois = "sair"
        self._desde = agora + segundos

    def _bateria(self, agora):
        bat = self.app.bateria
        resta = bat.restante_m() if bat.carga else None
        if resta is None:
            # ainda não dá para prever: nada de chutar com a voz, só o que se sabe, escrito
            self._mostrar_e_sair(bat.texto_previsao() if bat.carga else
                                 "Toque em \"Carreguei 100%\" no botão da bateria e nós contamos os km.", agora)
            return
        fraca = bat.barras <= 1 or resta <= AVISO_BATERIA_M
        self._falar("umbra_bateria_fraca" if fraca else "umbra_bateria_ok", "sair", agora,
                    "alerta" if fraca else "confirmou")
        self._rosto_faz("legenda", None, bat.texto_previsao())

    def _perto(self, categoria, agora):
        app = self.app
        if app.posicao is None:
            self._falar("umbra_nada_perto", "sair", agora, "confuso")
            return
        self._falar("umbra_farejando", "esperar", agora)
        self._buscando = True
        termos = next((t for nome, t in _categorias() if nome == categoria), ())
        origem = app.posicao

        def procurar():
            import busca
            return busca.perto_por_categoria(termos, origem, 1)

        def achou(lista):
            self._buscando = False
            if not self.conversando:
                return
            if not lista:
                self._falar("umbra_nada_perto", "sair", self._t, "confuso")
                return
            lugar = lista[0]
            self._rosto_faz("legenda", None, lugar.get("nome", ""))
            self._ir_para(dict(lugar))
            self._confirmando = True
            self._falar("umbra_achou", "ouvir", self._t, "confirmou")

        def falhou(erro):
            self._buscando = False
            if self.conversando:
                self._falar("umbra_nada_perto", "sair", self._t, "confuso")
        rodar = getattr(app, "em_segundo_plano", None)
        if rodar is None:
            import rede
            rodar = rede.em_segundo_plano
        rodar(procurar, achou, falhou)

    def _esperando_rota(self, agora):
        app = self.app
        if app.nav is not None:
            self.fechar(agora)
        elif getattr(app, "rota_previa", None) is not None:
            if agora - self._desde > INICIAR_DEPOIS_S:
                app.iniciar_navegacao()
                self.fechar(agora)
        elif getattr(app, "destino", None) is None or agora - self._desde > ESPERA_ROTA_MAX_S:
            self.fechar(agora)                         # cancelou, ou a rota não veio (a prévia avisa o porquê)

    # --- escutar o nome com a moto parada ---------------------------------------------
    def pausar(self):
        self.pausado = True
        if self.estado == VIGIA:
            self.escuta.parar()
            self.estado = OCULTO

    def retomar(self):
        self.pausado = False

    def _pode_vigiar(self, agora):
        app = self.app
        if self.pausado or not self.microfone or not app.ajustes["umbra_escuta"]:
            return False
        if self.voz.ocupada() or not self.escuta.disponivel():
            return False
        if app.velocidade_agora() >= PARADO_KMH:
            self._parado_desde = None
            return False
        if self._parado_desde is None:
            self._parado_desde = agora
        return agora - self._parado_desde >= PARADO_S

    def _vigiar(self, agora):
        if self.estado == VIGIA:
            if not self._pode_vigiar(agora):
                self.escuta.parar()
                self.estado = OCULTO
                return
            sit = self.escuta.situacao()
            if sit == "entendeu":
                sim, resto = chamado(self.escuta.alternativas())
                self.estado = OCULTO
                if sim:
                    tela = getattr(self.app, "sm", None)
                    if tela is not None and tela.current != "mapa":
                        tela.current = "mapa"
                    self.chamar(resto, agora)
                else:
                    self._vigia_volta = agora + VIGIA_PAUSA_S
            elif sit in ("nada", "parada", "sem"):
                self.estado = OCULTO
                erro = self.escuta.erro()
                # 6/7 = silêncio, nada parecido com fala (normal); o resto é falha: espera mais
                self._vigia_volta = agora + (VIGIA_PAUSA_S if erro in (0, 6, 7) else VIGIA_PAUSA_ERRO_S)
                if erro == 9:                      # sem permissão do microfone
                    self.microfone = False
            elif agora - self._desde > OUVIR_MAX_S:
                self.escuta.parar()
                self.estado = OCULTO
            return
        if agora >= self._vigia_volta and self._pode_vigiar(agora):
            self.estado = VIGIA
            self._desde = agora
            self.escuta.ouvir(0.8)


AVISO_BATERIA_M = 6000      # com menos que isso pela frente, "bateria fraca"


def _categorias():
    import busca
    return busca.CATEGORIAS_PERTO
