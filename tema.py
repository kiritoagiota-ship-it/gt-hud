"""Paleta e medidas do HUD. Tudo que é visual e se repete fica aqui."""
from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex as hexc

# Cores
FUNDO = hexc("#04070B")          # quase preto azulado: contraste alto no sol
PAINEL = hexc("#0A1520")         # fundo de blocos
PAINEL_CLARO = hexc("#12283A")   # topo do degradê de painéis e botões
CIANO = hexc("#00E5FF")          # cor principal do sistema
CIANO_APAGADO = hexc("#0D3440")  # segmentos apagados do anel
CIANO_FRACO = hexc("#4FA8B8")    # rótulos secundários
BRANCO = hexc("#F2FBFF")
LARANJA = hexc("#FF8A00")        # alerta de limite
VERMELHO = hexc("#FF3355")       # erro / sem sinal
VERDE = hexc("#3DFFA2")          # GPS bom


def com_alfa(cor, alfa):
    return (cor[0], cor[1], cor[2], alfa)


# Tipografia (fonte padrão do Kivy; textos só em ASCII para evitar
# os problemas de renderização que já apareceram no TraveteFocus)
T_ROTULO = sp(13)
T_VALOR = sp(34)
T_BOTAO = sp(17)
T_TITULO = sp(22)

MARGEM = dp(14)

# Fim da escala do velocímetro (a GT20 anda até uns 45 km/h)
VEL_MAXIMA = 50
