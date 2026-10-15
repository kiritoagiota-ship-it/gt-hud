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
import re
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


# "não" perto do pedido desfaz o pedido: "não vai", "pode não", "vai pra casa não"
NEGACOES = ("nao", "nem", "nunca", "jamais")
NEGA_FRASES = ("nao quero", "nao precisa", "nem pensar", "deixa pra la", "agora nao", "melhor nao")
# "me leva pro Flamboyant", "bora pra rodoviária": o que vem depois é o destino
_IR = re.compile(r"(?:^| )(?:me leva|leva eu|leva a gente|me levar|levar|leva|vamos|vamo|bora|partiu|quero ir|"
                 r"ir|vai|navega|navegar|rota|me guia|guia)"
                 r"(?: (?:ate|para|pra|pro|pros|pras|ao|aos|a|o|as|os|no|na))+ (.+)$")
_SOBRA_FIM = NEGACOES + ("agora", "ai", "logo", "rapido", "favor", "por", "ja")
_ARTIGOS = ("o", "a", "os", "as", "um", "uma")
_PERTO_FIM = ("mais perto", "mais proximo", "mais proxima", "aqui perto", "perto", "proximo", "proxima")
_PERGUNTAS = ("que", "qual", "quais", "como", "quando", "quem", "quanto", "quantos", "quantas", "porque",
              "por que", "cade")
LUGAR_MAX_PALAVRAS = 4    # resposta curta e sem sentido ("Flamboyant"): ele tenta como nome de lugar


def normalizar(texto):
    """Minúsculas, sem acento e sem pontuação: "Me leva pra CASA!" -> "me leva pra casa"."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = "".join(c if c.isalnum() else " " for c in t)
    return " ".join(t.split())


def _tem(texto, palavra):
    """A palavra (ou expressão) aparece inteira no texto normalizado."""
    return (" %s " % normalizar(palavra)) in (" %s " % texto)


def _posicao(texto, palavra):
    """Em que palavra do texto (normalizado) a expressão começa; -1 se não aparece."""
    i = (" %s " % texto).find(" %s " % normalizar(palavra))
    return -1 if i < 0 else len(texto[:i].split())


def _negado(texto, k):
    """O pedido que começa na palavra k foi negado? "não vai", "pode não", "não quero ir pra casa"."""
    p = texto.split()
    if not p:
        return False
    if p[-1] in NEGACOES or any(_tem(texto, f) for f in NEGA_FRASES):
        return True
    return any(w in NEGACOES for w in p[max(0, k - 2):max(0, k)])


def _destino(texto):
    """(destino, palavra em que o pedido começa) de "me leva pro shopping flamboyant", ou (None, -1)."""
    m = _IR.search(texto)
    if not m:
        return None, -1
    d = m.group(1).split()
    while d and d[-1] in _SOBRA_FIM:
        d.pop()
    while d and d[0] in _ARTIGOS:
        d.pop(0)
    return (" ".join(d) or None), len(texto[:m.start()].split()) + (1 if m.start() > 0 else 0)


def _categoria_exata(destino):
    """"farmácia", "um mercado mais perto" -> a categoria; "padaria do zé" -> None (é um lugar)."""
    d = destino
    for fim in _PERTO_FIM:
        if d.endswith(" " + fim):
            d = d[:-len(fim) - 1]
            break
    d = " ".join(w for w in d.split() if w not in _ARTIGOS)
    for categoria, palavras in _PERTO:
        if d in tuple(normalizar(p) for p in palavras):
            return categoria
    return None


def parece_lugar(texto):
    """Uma resposta curta e não entendida pode ser só o nome do lugar ("Flamboyant")."""
    t = normalizar(texto)
    return 0 < len(t.split()) <= LUGAR_MAX_PALAVRAS and not any(_tem(t, q) for q in _PERGUNTAS)


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

    def achou(palavras):
        ks = [_posicao(t, p) for p in palavras]
        ks = [k for k in ks if k >= 0]
        return min(ks) if ks else -1
    k = achou(_PALAVRAS[0][1])                                  # cancelar vem antes de tudo
    if k >= 0:
        return ("negou", None) if _negado(t, k) else ("cancelar", None)
    destino, _k = _destino(t)                                  # "me leva pro Flamboyant"
    if destino:
        # aqui só o "não" do fim ou um "não quero" valem: "não, me leva pra casa" é um pedido
        if _negado(t, 0):
            return "negou", None
        for nome, palavras in _PALAVRAS[1:3]:                  # casa, trabalho
            if destino in tuple(normalizar(p) for p in palavras) or destino in ("meu " + normalizar(p) for p in palavras):
                return nome, None
        categoria = _categoria_exata(destino)
        return ("perto", categoria) if categoria else ("lugar", destino)
    for categoria, palavras in _PERTO:                        # "farmácia mais perto"
        k = achou(palavras)
        if k >= 0:
            return ("negou", None) if _negado(t, k) else ("perto", categoria)
    for nome, palavras in _PALAVRAS[1:]:
        k = achou(palavras)
        if k >= 0:
            if nome in ("casa", "trabalho", "rotas", "iniciar") and _negado(t, k):
                return "negou", None
            return nome, None
    return "desconhecido", None


def entender_alternativas(alternativas):
    """A primeira alternativa do reconhecedor que dá uma intenção conhecida. Buscar um lugar pelo
    nome fica por último: "me leva pra cara" (ouvido errado) perde para "me leva pra casa"."""
    primeira = lugar = None
    for alt in alternativas:
        r = entender(alt)
        if primeira is None:
            primeira = r
        if r[0] == "lugar":
            lugar = lugar or (r, alt)
        elif r[0] not in ("desconhecido", "nada_dito"):
            return r, alt
    if lugar:
        return lugar
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
ANDANDO_KMH = 8.0           # já escutando, só para acima disso (o GPS parado oscila uns km/h à toa)
OUVIR_MAX_S = 12.0          # uma escuta que não termina sozinha
# paciência (pedido do dono, 15/10/2026: "não passa nem 2 segundos e ele acha que eu tô inativo"): o
# reconhecedor do celular devolve "nada" logo depois de pouco silêncio; enquanto não passar isso desde
# que ele começou a ouvir o pedido, ele volta a ouvir calado, sem contar como silêncio
PACIENCIA_S = 8.0
RECOMECO_S = 0.25           # entre uma escuta que voltou vazia e a próxima
ERROS_DE_SILENCIO = (0, 6, 7)   # (escuta.ERROS) sem fala / nada parecido com fala: vale esperar mais
# agir antes do fim da frase: o que o reconhecedor já entendeu no meio da fala (o "parcial") e
# ficou parado esse tempo vale como o pedido, sem esperar o silêncio e o resultado final (~1 s)
PARCIAL_ESTAVEL_S = 0.5
PARCIAL_CURTO_S = 0.8       # palavra solta ("sim", "valeu", "não"): espera um pouco mais (pode vir mais)
DECIDE_NO_PARCIAL = ("casa", "trabalho", "cancelar", "rotas", "bateria", "perto", "valeu", "tchau", "negou",
                     "iniciar")
CURTAS = ("iniciar", "valeu", "tchau", "negou")
ESPERA_ROTA_MAX_S = 30.0
INICIAR_DEPOIS_S = 1.2      # a rota apareceu: um instante para ver antes de começar
ESPERA_TRANQUILA_MAX_S = 20.0   # preferida "Tranquila": espera ela chegar (uns 7 s) antes de sair navegando
FOLGA_FALA_S = 0.5          # depois de pedir uma fala, o tempo para ela começar
VIGIA_PAUSA_S = 0.4         # entre uma escuta do nome e a próxima
VIGIA_PAUSA_ERRO_S = 2.5    # o reconhecedor falhou (sem internet, ocupado): espera um pouco (vem um novo)
VIGIA_PAUSA_LIMITE_S = 15.0  # "pedidos demais" (erro 10): o Google pediu calma
NOME_PARCIAL_S = 0.35       # o nome apareceu no meio da fala e nada veio depois: já atende
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
        self._ultima = {}                   # a última frase sorteada de cada grupo (não repete seguida)
        self._parcial_nome = None           # o nome apareceu no resultado parcial (e desde quando)
        self._parcial_desde = 0.0
        self._voltar_a_avisar = False       # anota no diagnóstico quando volta a escutar o nome
        self._conversa = 0                  # muda a cada conversa: resposta de busca de uma conversa velha é ignorada
        self._avisou_tranquila = False
        self._ouvindo_desde = 0.0           # quando começou a ouvir o pedido (a paciência conta daqui)
        self._recomeco = None               # hora de voltar a ouvir (a escuta voltou vazia cedo demais)
        self._parcial_txt = ""              # o que ele já ouviu no meio da fala, e desde quando está igual
        self._parcial_t = 0.0
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

    def _na_tela(self, funcao):
        """Resposta da internet: com o app minimizado ela chega na thread de segundo plano, que
        não pode mexer na tela; fica para quando o app voltar (app.na_tela)."""
        na_tela = getattr(self.app, "na_tela", None)
        if na_tela is None:
            funcao()
        else:
            na_tela(funcao)

    # --- falar -------------------------------------------------------------------
    def _falar(self, chave, depois, agora, estado_rosto="falando"):
        self.voz.falar([chave], P_UMBRA)
        self.estado = RESPONDENDO if self.estado not in (SAUDANDO,) else SAUDANDO
        self._depois = depois
        self._desde = agora
        self._rosto_faz("definir_estado", estado_rosto)
        self._rosto_faz("legenda", None, falas.GRAVADAS.get(chave, ""))

    def _sorteia(self, *chaves):
        """Uma das frases, nunca a mesma da última vez (do mesmo grupo)."""
        opcoes = [c for c in chaves if c != self._ultima.get(chaves)] or list(chaves)
        c = opcoes[self.sorteio.randrange(len(opcoes))]
        self._ultima[chaves] = c
        return c

    def _uma(self, base):
        """Sorteia entre a frase e as variações gravadas dela (base, base_1, base_2...)."""
        return self._sorteia(*_familia(base))

    # --- chamar (botão ou nome) ----------------------------------------------------
    @property
    def conversando(self):
        return self.estado in (SAUDANDO, OUVINDO, RESPONDENDO, ESPERANDO_ROTA)

    def chamar(self, resto="", agora=None):
        agora = self._t if agora is None else agora
        if self.conversando:
            return
        print("[umbra] chamado" + (" pelo nome" if self.estado == VIGIA or resto else ""), flush=True)
        self._voltar_a_avisar = True
        self.escuta.parar()
        self._silencios = self._sem_entender = 0
        self._confirmando = False
        self._nova_conversa()
        self._rosto_faz("olhar_para", 0)
        # andando, ele vem médio no canto e sem escurecer o mapa (pedido do dono, 14/10/2026)
        self._rosto_faz("mostrar", "medio" if self._andando() else "grande")
        self._rosto_faz("acordar")              # ouviu o nome: os olhos acendem num lampejo, a cabeça levanta
        self._rosto_faz("legenda", "", "")
        if resto:
            self._rosto_faz("legenda", resto, "")
            self.estado = OUVINDO
            self._desde = agora
            self._processar([resto], agora)
            return
        self.estado = SAUDANDO
        self._falar(self._uma("umbra_andando" if self._andando() and "umbra_andando" in falas.UMBRA else "umbra_oi"),
                    "ouvir", agora)

    def _andando(self):
        try:
            return self.app.velocidade_agora() >= PARADO_KMH
        except Exception:
            return False

    def _lado_da_curva(self):
        """-1/1: a próxima curva da rota é para a esquerda/direita (0: reto ou sem rota)."""
        try:
            acao = ((self.app.estado_nav or {}).get("manobra") or {}).get("acao") or ""
        except Exception:
            return 0
        return -1 if "esquerda" in acao else (1 if "direita" in acao else 0)

    def _nova_conversa(self):
        """Uma busca que ainda não respondeu fica para trás: a resposta dela não vale mais."""
        self._conversa += 1
        self._buscando = False
        self._avisou_tranquila = False

    def fechar(self, agora=None, calar=False):
        """Some (terminou, ou o dono tocou nele / apertou Voltar). calar: o dono o dispensou,
        então a frase que ele estava dizendo para no meio (antes ele sumia e seguia falando)."""
        if calar and self.estado in (SAUDANDO, RESPONDENDO):
            self.voz.calar()
        self.escuta.parar()
        self.estado = OCULTO
        self._depois = None
        self._confirmando = False
        self._nova_conversa()
        self._rosto_faz("esconder")

    # --- os avisos da navegação: o Umbra pequeno -------------------------------------
    def ao_falar(self, pedacos):
        """A voz começou uma fala (voz.ao_tocar). Se for um dos avisos escolhidos, o Umbra
        pequeno aparece enquanto ela dura."""
        if self.conversando or not pedacos:
            return
        if self.pausado:
            # app minimizado: quem chama aqui é a thread de segundo plano (a fala da navegação), e
            # tela não se mexe fora da thread do Kivy. Até a 1.0.94 o rosto "aparecia" escondido
            # e a etapa do desenho ficava marcada: fechado assim, o app achava na abertura seguinte
            # que o desenho do Umbra tinha derrubado o app e rebaixava o rosto à toa.
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
        self._rosto_faz("olhar_para", self._lado_da_curva() if navegando and humor != "confirmou" else 0)

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
            self._rosto_faz("definir_estado", "pensando")   # já farejou: agora pensa até a resposta chegar
            return
        if depois == "ouvir":
            self._ouvir(agora)
        elif depois == "rota":
            self.estado = ESPERANDO_ROTA
            self._desde = agora
            self._rosto_faz("definir_estado", "pensando")   # calculando a rota
        else:
            self.fechar(agora)

    def escuta_falhou(self):
        """O reconhecimento de voz derrubou o app nesta versão (diagnostico.etapa): não escuta."""
        try:
            return self.app.ajustes["umbra_escuta_falhou"] == self.app.versao()
        except Exception:
            return False

    def _ouvir(self, agora):
        if self.escuta_falhou():
            self._mostrar_e_sair("O reconhecimento de voz fechou o app neste celular. Deixamos a escuta "
                                 "desligada até a próxima versão.", agora, 5.0)
            return
        self.estado = OUVINDO
        self._desde = self._ouvindo_desde = agora
        self._recomeco = None
        self._parcial_txt = ""
        self._rosto_faz("definir_estado", "ouvindo")
        self.escuta.ouvir(1.2)

    def _ouvindo(self, agora):
        if self._recomeco is not None:               # a escuta voltou vazia cedo: daqui a pouco ouve de novo
            if agora >= self._recomeco:
                self._recomeco = None
                self._desde = agora
                self._parcial_txt = ""
                self.escuta.ouvir(1.2)
            return
        sit = self.escuta.situacao()
        if sit == "entendeu":
            alternativas = self.escuta.alternativas()
            self._rosto_faz("legenda", alternativas[0] if alternativas else "", "")
            self._processar(alternativas, agora)
        elif sit == "sem":
            self._falar("umbra_tchau", "sair", agora)
            # (depois da fala: _falar põe a frase dita na legenda e apagava o motivo)
            self._rosto_faz("legenda", None, "O celular não tem reconhecimento de voz.")
        elif sit in ("nada", "parada") and agora - self._desde > 0.3 or agora - self._desde > OUVIR_MAX_S:
            self.escuta.parar()
            vazia = sit in ("nada", "parada") and self.escuta.erro() in ERROS_DE_SILENCIO
            if vazia and agora - self._ouvindo_desde < PACIENCIA_S:
                # ainda dentro da paciência: a pessoa pode estar pensando no que pedir; ele segue
                # ouvindo, calado (até a 1.0.95 já perguntava "tá aí?" em menos de 2 s)
                self._recomeco = agora + RECOMECO_S
                return
            self._silencios += 1
            if self._silencios == 1:
                self._falar(self._uma("umbra_silencio"), "ouvir", agora, "confuso")
            else:
                self._falar(self._uma("umbra_tchau"), "sair", agora)
        else:
            self._parcial_conversa(agora)

    def _parcial_conversa(self, agora):
        """Ele age antes do fim da frase: o que o reconhecedor já entendeu no meio da fala, parado há
        PARCIAL_ESTAVEL_S e com um pedido claro ("me leva pra casa"), vale sem esperar o silêncio e o
        resultado final (~1 s a menos em cada resposta). Enquanto a pessoa fala, o que ele já ouviu
        aparece na legenda."""
        texto = (self.escuta.parcial() or "").strip()
        if not texto:
            return
        if texto != self._parcial_txt:
            self._parcial_txt, self._parcial_t = texto, agora
            self._rosto_faz("legenda", texto, None)
            return
        intencao = entender(texto)[0]
        if intencao not in DECIDE_NO_PARCIAL:
            return                                   # um lugar pelo nome pode ainda estar crescendo: espera o fim
        if agora - self._parcial_t < (PARCIAL_CURTO_S if intencao in CURTAS else PARCIAL_ESTAVEL_S):
            return
        self.escuta.parar()
        self._parcial_txt = ""
        print("[umbra] entendeu no meio da fala: %s" % intencao, flush=True)
        self._processar([texto], agora)

    # --- o que fazer com o pedido ------------------------------------------------------
    def _processar(self, alternativas, agora):
        (intencao, dado), texto = entender_alternativas(alternativas)
        self.ultimo_pedido = (intencao, dado)
        app = self.app
        if self._confirmando:                      # perguntou "Vamos?"
            self._confirmando = False
            if intencao == "iniciar":
                self._falar("rota_calculada", "rota", agora, "confirmou")
                return
            if intencao in ("tchau", "cancelar", "negou"):
                if app.nav is None and (getattr(app, "rota_previa", None) is not None
                                        or getattr(app, "destino", None) is not None):
                    app.cancelar_previa()
                self._falar(_ou("umbra_ok_nao", "umbra_tchau"), "sair", agora)
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
        elif intencao == "lugar":
            self._lugar(dado, agora)
        elif intencao == "negou":
            self._falar(_ou("umbra_ok_nao", "umbra_tchau"), "sair", agora)
        elif intencao == "cancelar":
            if app.nav is not None:
                app.encerrar_navegacao()
                self.voz.calar()                       # (no lugar do "navegação encerrada")
            elif getattr(app, "rota_previa", None) is not None or getattr(app, "destino", None) is not None:
                app.cancelar_previa()
            self._falar(self._uma("umbra_cancelada"), "sair", agora, "confirmou")
        elif intencao == "iniciar":
            if getattr(app, "rota_previa", None) is not None and app.nav is None:
                self._falar("rota_calculada", "rota", agora, "confirmou")
            else:
                self._falar("umbra_oi_2", "ouvir", agora)
        elif intencao == "valeu":
            self._falar(self._uma("umbra_valeu"), "sair", agora, "confirmou")
        elif intencao == "tchau":
            self._falar(self._uma("umbra_tchau"), "sair", agora)
        elif self._sem_entender == 0 and parece_lugar(texto):
            self._lugar(normalizar(texto), agora, tentativa=True)   # "Flamboyant": talvez seja o lugar
        else:
            self._nao_entendeu(agora)

    def _nao_entendeu(self, agora):
        self._sem_entender += 1
        # cara fechada no "não entendi" (pedido do dono, 15/10/2026): sobrancelha baixa, rosnado leve
        if self._sem_entender <= 2:
            self._falar(self._uma("umbra_nao_entendi"), "ouvir", agora, "irritado")
        else:
            self._falar(self._uma("umbra_tchau"), "sair", agora, "irritado")

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
        self._falar("umbra_farejando", "esperar", agora, "farejando")
        self._buscando = True
        termos = next((t for nome, t in _categorias() if nome == categoria), ())
        origem = app.posicao
        minha = self._conversa

        def procurar():
            import busca
            return busca.perto_por_categoria(termos, origem, 1)

        def achou(lista):
            if minha != self._conversa or not self.conversando:
                return                 # a conversa dessa busca já acabou: não troca o destino de agora
            self._buscando = False
            if not lista:
                self._falar("umbra_nada_perto", "sair", self._t, "confuso")
                return
            lugar = lista[0]
            self._ir_para(dict(lugar))
            self._confirmando = True
            self._falar("umbra_achou", "ouvir", self._t, "confirmou")
            self._rosto_faz("legenda", None, _texto_do_lugar(lugar))   # (depois da fala: senão ela apaga)

        def falhou(erro):
            if minha != self._conversa or not self.conversando:
                return
            self._buscando = False
            self._falar("umbra_nada_perto", "sair", self._t, "confuso")
        self._rodar(procurar, achou, falhou)

    def _rodar(self, procurar, achou, falhou):
        """procurar() numa thread; achou/falhou de volta na tela."""
        rodar = getattr(self.app, "em_segundo_plano", None)
        if rodar is None:
            import rede
            rodar = rede.em_segundo_plano
        rodar(procurar, lambda r: self._na_tela(lambda: achou(r)), lambda e: self._na_tela(lambda: falhou(e)))

    def _lugar(self, nome, agora, tentativa=False):
        """"Me leva pro Flamboyant": busca o lugar (a mesma busca da tela), mostra a rota e
        pergunta "Vamos?". tentativa: era só uma resposta não entendida; se não achar nada,
        vira "não entendemos"."""
        app = self.app
        self._falar(_ou("umbra_procurando", "umbra_farejando"), "esperar", agora, "farejando")
        self._rosto_faz("legenda", nome, None)
        self._buscando = True
        origem = app.posicao
        salvos = list(getattr(app, "salvos", None) or [])
        try:
            chave = (app.ajustes["tomtom"] or "").strip() or None
        except Exception:
            chave = None
        minha = self._conversa

        def procurar():
            import busca
            return busca.buscar(nome, origem, salvos, chave)

        def nada():
            if tentativa:
                self._nao_entendeu(self._t)
            else:
                self._falar(_ou("umbra_nao_achou", "umbra_nada_perto"), "sair", self._t, "confuso")

        def achou(lista):
            if minha != self._conversa or not self.conversando:
                return                 # a conversa dessa busca já acabou: não troca o destino de agora
            self._buscando = False
            lista = [l for l in (lista or []) if l.get("lat") is not None]
            if not lista:
                nada()
                return
            lugar = _o_de_goiania(lista)
            self._ir_para(dict(lugar))
            self._confirmando = True
            self._falar(_ou("umbra_lugar_achado", "umbra_achou"), "ouvir", self._t, "confirmou")
            # o nome e o endereço DEPOIS da fala: ele pergunta "É esse aí?" e a pessoa precisa ver
            # qual (até a 1.0.94 a frase apagava a legenda na hora)
            self._rosto_faz("legenda", None, _texto_do_lugar(lugar))

        def falhou(erro):
            if minha != self._conversa or not self.conversando:
                return
            self._buscando = False
            nada()
        self._rodar(procurar, achou, falhou)

    def _quer_tranquila(self):
        """A preferida nos Ajustes é a Tranquila e ela ainda está sendo calculada (a mais rápida
        chega primeiro, a tranquila uns 7 s depois)."""
        app = self.app
        try:
            if app.ajustes["rota_preferida"] != "tranquila" or not getattr(app, "calculando_alternativas", False):
                return False
        except (KeyError, TypeError):
            return False
        return "tranquila" not in (getattr(app.rota_previa, "nome_perfil", "") or "")

    def _esperando_rota(self, agora):
        app = self.app
        if app.nav is not None:
            self.fechar(agora)
        elif getattr(app, "rota_previa", None) is not None:
            if agora - self._desde <= INICIAR_DEPOIS_S:
                return
            if self._quer_tranquila() and agora - self._desde < ESPERA_TRANQUILA_MAX_S:
                # pedido pela voz respeita a preferida: até a 1.0.94 ele saía pela mais rápida
                if not self._avisou_tranquila:
                    self._avisou_tranquila = True
                    self._rosto_faz("legenda", None, "Buscando a rota mais tranquila...")
                return
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
        if self.pausado or not self.microfone or not app.ajustes["umbra_escuta"] or self.escuta_falhou():
            return False
        if self.voz.ocupada() or not self.escuta.disponivel():
            return False
        if app.velocidade_agora() >= (ANDANDO_KMH if self.estado == VIGIA else PARADO_KMH):
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
                    self._ouviu_o_nome(resto, agora)
                else:
                    self._vigia_volta = agora + VIGIA_PAUSA_S
            elif sit in ("nada", "parada", "sem"):
                self.estado = OCULTO
                erro = self.escuta.erro()
                # 6/7 = silêncio, nada parecido com fala (normal); o resto é falha: espera mais
                self._vigia_volta = agora + (VIGIA_PAUSA_S if erro in (0, 6, 7) else
                                             VIGIA_PAUSA_LIMITE_S if erro == 10 else VIGIA_PAUSA_ERRO_S)
                if erro == 9:                      # sem permissão do microfone
                    self.microfone = False
            else:
                # o nome já apareceu no meio da fala e nada veio depois dele: atende sem esperar o
                # fim da escuta (o silêncio e a resposta final do reconhecedor levam ~1 s a mais)
                parcial = self.escuta.parcial()
                sim, resto = chamado([parcial]) if parcial else (False, "")
                if sim and not resto:
                    if parcial != self._parcial_nome:
                        self._parcial_nome, self._parcial_desde = parcial, agora
                    elif agora - self._parcial_desde >= NOME_PARCIAL_S:
                        self._parcial_nome = None
                        self.escuta.parar()
                        self.estado = OCULTO
                        print("[umbra] ouviu o nome no meio da fala", flush=True)
                        self._ouviu_o_nome("", agora)
                        return
                else:
                    self._parcial_nome = None
                if agora - self._desde > OUVIR_MAX_S:
                    self.escuta.parar()
                    self.estado = OCULTO
            return
        if agora >= self._vigia_volta and self._pode_vigiar(agora):
            self.estado = VIGIA
            self._desde = agora
            self._parcial_nome = None
            if self._voltar_a_avisar:
                self._voltar_a_avisar = False
                print("[escuta] voltou a escutar o nome", flush=True)
            self.escuta.ouvir(0.8, conversa=False)

    def _ouviu_o_nome(self, resto, agora):
        tela = getattr(self.app, "sm", None)
        if tela is not None and tela.current != "mapa":
            tela.current = "mapa"
        self.chamar(resto, agora)


# com menos que isso pela frente, "bateria fraca": o MESMO limite do aviso automático (bateria.py);
# até a 1.0.94 aqui era 6 km e lá 5 km
from bateria import AVISO_BAIXA_M as AVISO_BATERIA_M  # noqa: E402


def _texto_do_lugar(lugar):
    """O que vai na legenda quando ele acha um lugar: o nome e, embaixo, o endereço."""
    texto = lugar.get("nome", "")
    if lugar.get("endereco"):
        texto += "\n" + lugar["endereco"]
    return texto


def _familia(base):
    """A frase e as variações gravadas dela: "umbra_oi" -> umbra_oi_1, umbra_oi_2..."""
    chaves = sorted(k for k in falas.UMBRA if k == base or (k.startswith(base + "_") and k[len(base) + 1:].isdigit()))
    return tuple(chaves) or (base,)


def _ou(chave, reserva):
    """A frase nova, se já foi gravada; senão a que já existe."""
    return chave if chave in falas.UMBRA else reserva


def _o_de_goiania(lista):
    """O primeiro resultado dentro de Goiânia (o app só navega na cidade); senão o primeiro."""
    try:
        import goiania
        for lugar in lista:
            if goiania.dentro(lugar["lat"], lugar["lon"], 0.01):
                return lugar
    except Exception:
        pass
    return lista[0]


def _categorias():
    import busca
    return busca.CATEGORIAS_PERTO
