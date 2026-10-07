"""Aviso de chuva no caminho (escolhido pelo dono em 08/10/2026).

Previsão do Open-Meteo (gratuito, sem conta nem chave): precipitação de 15
em 15 minutos para as próximas 2 horas, no ponto pedido. O app olha a saída
(a próxima meia hora) e o destino (até a hora de chegar, mais uma folga) e
avisa a primeira chuva que achar.

É PREVISÃO, não radar: pancada de verão pode vir sem aviso, ou o aviso pode
não se confirmar. Por isso a frase diz "previsão de chuva".
"""
import urllib.parse

import rede

URL = "https://api.open-meteo.com/v1/forecast"
CHUVA_MM = 0.2          # em 15 min: a partir disso molha
CHUVA_FORTE_MM = 2.0
PROVAVEL = 65           # % de chance: com isso avisa mesmo sem milímetros previstos
FOLGA_CHEGADA_MIN = 20  # olha o destino até a chegada + isso


def previsao(lat, lon):
    """[(minutos a partir de agora, mm em 15 min, % de chance)] das próximas 2 h.
    Chamada que espera a resposta (use rede.em_segundo_plano)."""
    consulta = urllib.parse.urlencode({
        "latitude": "%.4f" % lat, "longitude": "%.4f" % lon,
        "minutely_15": "precipitation,precipitation_probability",
        "forecast_minutely_15": 9, "timezone": "auto"})
    dados = rede.baixar_json(URL + "?" + consulta, timeout=10)
    quartos = dados.get("minutely_15") or {}
    mm = quartos.get("precipitation") or []
    chance = quartos.get("precipitation_probability") or []
    return [(k * 15, float(mm[k] or 0.0), float(chance[k] or 0.0) if k < len(chance) else 0.0)
            for k in range(len(mm))]


def _primeira_chuva(faixas, ate_min):
    for minutos, mm, chance in faixas:
        if minutos > ate_min:
            break
        if mm >= CHUVA_MM or (chance >= PROVAVEL and mm > 0):
            return minutos, mm
    return None


def chuva(origem, destino, duracao_s, prever=previsao):
    """Chuva prevista na saída ou no destino: {"em_min", "onde", "forte"} ou
    None. Chamada que espera a resposta."""
    achados = []
    saida = _primeira_chuva(prever(*origem), 30)
    if saida is not None:
        achados.append((saida[0], "saida", saida[1]))
    chegada_min = duracao_s / 60.0 + FOLGA_CHEGADA_MIN
    no_destino = _primeira_chuva(prever(*destino), min(120, chegada_min))
    if no_destino is not None:
        achados.append((no_destino[0], "destino", no_destino[1]))
    if not achados:
        return None
    minutos, onde, mm = min(achados)
    return {"em_min": int(minutos), "onde": onde, "forte": mm >= CHUVA_FORTE_MM}


def frase(c):
    """Texto curto para a tela."""
    if c is None:
        return ""
    tipo = "Chuva forte" if c["forte"] else "Chuva"
    lugar = "na saída" if c["onde"] == "saida" else "no destino"
    if c["em_min"] <= 0:
        return "%s prevista agora %s" % (tipo, lugar)
    return "%s prevista em ~%d min %s" % (tipo, c["em_min"], lugar)


def fala(c):
    """Frase para o assistente dizer."""
    tipo = "chuva forte" if c["forte"] else "chuva"
    lugar = "na saída" if c["onde"] == "saida" else "no destino"
    if c["em_min"] <= 0:
        return "Atenção: previsão de %s agora %s." % (tipo, lugar)
    return "Atenção: previsão de %s em %d minutos %s." % (tipo, c["em_min"], lugar)
