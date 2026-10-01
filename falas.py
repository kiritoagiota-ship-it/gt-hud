"""Tudo o que o assistente fala: chave -> texto.

ferramentas/gerar_voz.py grava cada fala em voz/<chave>.wav (no PC, com a
voz escolhida) e voz.py junta os pedaços numa frase na hora, por exemplo
["senhor", "em_200", "subida_8"] -> "Senhor, em duzentos metros, subida de
oito por cento." Nome de rua não é falado (a voz é gravada antes): ele
aparece na tela.
"""
DISTANCIAS = {
    50: "cinquenta metros", 100: "cem metros", 150: "cento e cinquenta metros",
    200: "duzentos metros", 250: "duzentos e cinquenta metros", 300: "trezentos metros",
    400: "quatrocentos metros", 500: "quinhentos metros", 600: "seiscentos metros",
    700: "setecentos metros", 800: "oitocentos metros", 900: "novecentos metros",
    1000: "um quilômetro", 1500: "um quilômetro e meio", 2000: "dois quilômetros",
}
_NUMEROS = {
    3: "três", 4: "quatro", 5: "cinco", 6: "seis", 7: "sete", 8: "oito", 9: "nove",
    10: "dez", 11: "onze", 12: "doze", 13: "treze", 14: "catorze", 15: "quinze",
    16: "dezesseis", 17: "dezessete", 18: "dezoito", 19: "dezenove", 20: "vinte",
}
_ORDINAIS = {1: "primeira", 2: "segunda", 3: "terceira", 4: "quarta", 5: "quinta"}
SUBIDA_MIN, SUBIDA_MAX = min(_NUMEROS), max(_NUMEROS)
ROTATORIA_MAX = max(_ORDINAIS)

FALAS = {"senhor": "Senhor,"}
for _m, _t in DISTANCIAS.items():
    FALAS["em_%d" % _m] = "Em %s," % _t
FALAS.update({
    "vire_esquerda": "vire à esquerda.",
    "vire_direita": "vire à direita.",
    "levemente_esquerda": "vire levemente à esquerda.",
    "levemente_direita": "vire levemente à direita.",
    "acentuada_esquerda": "faça uma curva fechada à esquerda.",
    "acentuada_direita": "faça uma curva fechada à direita.",
    "retorno": "faça o retorno.",
    "em_frente": "siga em frente.",
    "mantenha_esquerda": "mantenha-se à esquerda.",
    "mantenha_direita": "mantenha-se à direita.",
    "saida_esquerda": "pegue a saída à esquerda.",
    "saida_direita": "pegue a saída à direita.",
    "rotatoria": "entre na rotatória.",
    "sair_rotatoria": "saia da rotatória.",
    "chegara_destino": "você chegará ao destino.",
    "destino_direita": "o destino está à direita.",
    "destino_esquerda": "o destino está à esquerda.",
})
for _n, _t in _ORDINAIS.items():
    FALAS["rotatoria_%d" % _n] = "na rotatória, pegue a %s saída." % _t
for _g, _t in _NUMEROS.items():
    FALAS["subida_%d" % _g] = "subida de %s por cento." % _t
FALAS.update({
    "fim_subida": "Fim da subida.",
    "chegou": "você chegou ao destino.",
    "rota_calculada": "Rota calculada. Vamos lá.",
    "recalculando": "Recalculando a rota.",
    "sem_internet": "Estou sem internet para calcular a rota.",
    "navegacao_encerrada": "Navegação encerrada.",
    "gps_perdido": "perdi o sinal do GPS.",
    "gps_ok": "Sinal do GPS de volta.",
    "bem_vindo": "Sistemas online. Bem-vindo, senhor.",
})


def frase(pedacos):
    """Pedaços -> uma frase só, para o motor de voz do celular falar de uma
    vez (fluida), ex.: "Senhor, em duzentos metros, vire à direita." """
    partes = []
    for i, p in enumerate(pedacos):
        t = FALAS[p]
        if i and t[:1].isupper() and not t.startswith("GPS"):
            t = t[:1].lower() + t[1:]
        partes.append(t)
    texto = " ".join(partes)
    return texto[:1].upper() + texto[1:]


def resumo_rota(total_m, tempo_s, subida_m):
    """O que o assistente fala ao começar a navegação (só no motor do celular)."""
    km = ("%.1f" % (total_m / 1000.0)).replace(".", ",").replace(",0", "")
    minutos = max(1, int(round(tempo_s / 60.0)))
    texto = "Rota calculada, senhor. São %s quilômetros, cerca de %d minutos" % (km, minutos)
    if subida_m >= 15:
        texto += ", com %d metros de subida" % int(round(subida_m))
    return texto + ". Vamos lá."


def distancia_falada(metros):
    """A distância da lista mais perto de `metros` (para "Em X, ...")."""
    return min(DISTANCIAS, key=lambda m: abs(m - metros))


def chave_subida(grau):
    return "subida_%d" % max(SUBIDA_MIN, min(SUBIDA_MAX, int(round(grau))))


def texto_manobra(acao, saida=None):
    """Instrução para a tela, com as mesmas palavras da voz. (O texto que vem
    do Valhalla mistura inglês em algumas manobras, ex.: rotatória.)"""
    frase = FALAS[chave_manobra(acao, saida)].rstrip(".,")
    return frase[:1].upper() + frase[1:]


def chave_manobra(acao, saida=None):
    """Ação da rota (rota.py) -> fala da manobra."""
    if acao == "rotatoria":
        return "rotatoria_%d" % saida if saida and 1 <= saida <= ROTATORIA_MAX else "rotatoria"
    if acao in ("esquerda", "direita"):
        return "vire_" + acao
    if acao == "chegada":
        return "chegara_destino"
    if acao in ("chegada_direita", "chegada_esquerda"):
        return "destino_" + acao.split("_")[1]
    return acao if acao in FALAS else "em_frente"
