"""Paleta e medidas do HUD. Tudo que é visual e se repete fica aqui.

Dois temas (07/10/2026, pedido do dono): ESCURO (noite) e CLARO (dia, lê
melhor no sol). No automático, o app usa o claro entre o nascer e o pôr do
sol (calculados para a data e o lugar) e o escuro à noite.

As cores são LISTAS que nunca são trocadas por outras: aplicar() muda o
conteúdo delas no lugar. Assim, quem guardou uma referência (valor padrão
de propriedade, argumento padrão de função) continua valendo depois da
troca. O que já está desenhado só muda quando é redesenhado: por isso o app
remonta as telas ao trocar de tema (GTHudApp.trocar_tema).
"""
import math
import time

from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex as hexc

PALETAS = {
    "escuro": {
        "FUNDO": "#04070B",          # quase preto azulado
        "PAINEL": "#0A1520",         # fundo de blocos
        "PAINEL_CLARO": "#12283A",   # topo do degradê de painéis e botões
        "CIANO": "#00E5FF",          # cor principal do sistema
        "CIANO_APAGADO": "#0D3440",  # segmentos apagados do anel
        "CIANO_FRACO": "#4FA8B8",    # rótulos secundários
        "BRANCO": "#F2FBFF",         # texto principal
        "LARANJA": "#FF8A00",        # alerta de limite
        "VERMELHO": "#FF3355",       # erro / sem sinal
        "VERDE": "#3DFFA2",          # GPS bom
        "LUGAR": "#B8D6F0",          # nomes de bairro no mapa
        "ROXO": "#00E5FF",           # 2ª cor de brilho (só o tema Monarca tem uma diferente da principal)
    },
    # claro: fundo claro, texto escuro e as mesmas cores em tons mais fechados
    # (o ciano vivo e o verde-limão somem em cima de branco)
    "claro": {
        "FUNDO": "#E9EEF2",
        "PAINEL": "#FFFFFF",
        "PAINEL_CLARO": "#FFFFFF",
        "CIANO": "#00788F",
        "CIANO_APAGADO": "#C2D3DA",
        "CIANO_FRACO": "#4A6B78",
        "BRANCO": "#0A1A24",
        "LARANJA": "#C85A00",
        "VERMELHO": "#D01F40",
        "VERDE": "#0A8A50",
        "LUGAR": "#35546B",
        "ROXO": "#00788F",
    },
    # MONARCA DAS SOMBRAS (pedido do dono, 08/10/2026: "um tema mais estilo Venom ou Sung
    # Jin-woo"; ele escolheu este). Desenho próprio, só o CLIMA: preto arroxeado, janelas de
    # "sistema" em azul elétrico e um brilho roxo por trás. Nada de logotipo ou arte da obra.
    "monarca": {
        "FUNDO": "#05040C",
        "PAINEL": "#0B0920",
        "PAINEL_CLARO": "#1C1750",
        "CIANO": "#5AA0FF",          # o azul das janelas do sistema
        "CIANO_APAGADO": "#1B1A48",
        "CIANO_FRACO": "#9590E6",
        "BRANCO": "#EEF0FF",
        "LARANJA": "#FFA63D",
        "VERMELHO": "#FF3B6B",
        "VERDE": "#5CFFC8",
        "LUGAR": "#BDB6F5",
        "ROXO": "#9B5CFF",           # a aura das sombras
    },
}
DEGRADE = {"escuro": 0.72, "claro": 0.90, "monarca": 0.50}   # quanto da cor sobra na base do degradê
# As frases de alguns avisos mudam com o tema (no Monarca, o app fala como "o Sistema")
TEXTOS = {
    "monarca": {
        "chegou": "MISSÃO CONCLUÍDA", "encerrada": "MISSÃO ENCERRADA",
        "calculando": "O Sistema está traçando a rota...",
        "para_onde": "Qual é a missão?", "busca_titulo": "Qual é a missão?",
        "iniciar": "Aceitar", "cancelar": "Recusar",
        "subtitulo": "O SISTEMA DESPERTOU", "aviso": "[Sistema] ",
        "recompensas": "Recompensas da missão",
    },
}

modo = "escuro"
FUNDO, PAINEL, PAINEL_CLARO, CIANO, CIANO_APAGADO, CIANO_FRACO = ([0, 0, 0, 1] for _ in range(6))
BRANCO, LARANJA, VERMELHO, VERDE, LUGAR, ROXO = ([0, 0, 0, 1] for _ in range(6))
degrade_base = DEGRADE["escuro"]


def aplicar(nome):
    """Troca a paleta ("escuro", "claro" ou "monarca"), no lugar."""
    global modo, degrade_base
    modo = nome if nome in PALETAS else "escuro"
    for chave, cor in PALETAS[modo].items():
        globals()[chave][:] = hexc(cor)
    degrade_base = DEGRADE[modo]


def claro():
    return modo == "claro"


def monarca():
    return modo == "monarca"


def texto(chave, padrao):
    """A frase do aviso `chave` no tema de agora (ou `padrao`, a de sempre)."""
    return TEXTOS.get(modo, {}).get(chave, padrao)


def com_alfa(cor, alfa):
    return (cor[0], cor[1], cor[2], alfa)


def misturar(a, b, quanto):
    """Cor entre a e b (quanto = 0 dá a, 1 dá b), sem transparência."""
    return (a[0] + (b[0] - a[0]) * quanto, a[1] + (b[1] - a[1]) * quanto,
            a[2] + (b[2] - a[2]) * quanto, 1)


# --- dia ou noite ---------------------------------------------------------------------
FOLGA_SOL_MIN = 15   # o claro só entra/sai com o sol já um pouco acima do horizonte


def sol(lat, lon, quando=None):
    """(nascer, pôr) do sol em minutos desde a meia-noite, hora do celular,
    no dia de `quando` (time.struct_time local). Fórmula da NOAA (erro de
    poucos minutos). Sem nascer/pôr (regiões polares): None."""
    t = quando or time.localtime()
    g = 2 * math.pi / 365.0 * (t.tm_yday - 1)
    eq = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                   - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    la = math.radians(lat)
    c = math.cos(math.radians(90.833)) / (math.cos(la) * math.cos(decl)) - math.tan(la) * math.tan(decl)
    if not -1 <= c <= 1:
        return None
    ha = math.degrees(math.acos(c))
    fuso_min = (t.tm_gmtoff or 0) / 60.0
    return 720 - 4 * (lon + ha) - eq + fuso_min, 720 - 4 * (lon - ha) - eq + fuso_min


def e_noite(lat, lon, quando=None):
    """Já escureceu (depois do pôr do sol ou antes de nascer) no lugar e na hora dados?"""
    t = quando or time.localtime()
    s = sol(lat, lon, t)
    if s is None:
        return False
    agora = t.tm_hour * 60 + t.tm_min
    return agora < s[0] or agora >= s[1]


def modo_pela_hora(lat, lon, quando=None):
    """ "claro" de dia, "escuro" à noite, para o lugar e a hora dados."""
    t = quando or time.localtime()
    s = sol(lat, lon, t)
    if s is None:
        return "escuro"
    agora = t.tm_hour * 60 + t.tm_min
    return "claro" if s[0] + FOLGA_SOL_MIN <= agora < s[1] - FOLGA_SOL_MIN else "escuro"


aplicar("escuro")

# Tipografia (fonte padrão do Kivy; textos só em ASCII para evitar
# os problemas de renderização que já apareceram no TraveteFocus)
T_ROTULO = sp(13)
T_VALOR = sp(34)
T_BOTAO = sp(17)
T_TITULO = sp(22)

MARGEM = dp(14)

# Fim da escala do velocímetro (a GT20 anda até uns 45 km/h)
VEL_MAXIMA = 50
