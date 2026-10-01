"""Gera as falas do assistente (voz/<chave>.wav) a partir de falas.py.

Roda no PC com o Kokoro já instalado para o TraveteFocus (fica fora do APK):
  C:\\Users\\kirit\\travetefocus\\ferramentas\\voz\\venv\\Scripts\\python.exe ferramentas\\gerar_voz.py B
  (com AMOSTRAS <pasta> no lugar do B: grava uma amostra de cada voz para comparar)

A letra escolhe a voz (amostras mandadas ao dono em 30/09/2026):
  A = pm_alex (brasileira)
  B = pm_alex com 20% de bm_george (brasileira com um toque britânico)
  C = pm_santa (brasileira)
Voz ORIGINAL no estilo de assistente de IA: não imita a voz real do Jarvis
(ela pertence ao ator/dublador). O "efeito IA" é só numpy (ver efeito_ia).
"""
import os
import sys

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from falas import FALAS  # noqa: E402

PASTA_KOKORO = r"C:\Users\kirit\travetefocus\ferramentas\voz"
SAIDA = os.path.join(RAIZ, "voz")
TAXA = 22050          # mono 16 bits: ~44 KB por segundo de fala
VELOCIDADE = 0.98     # um pouco mais pausada: soa mais "assistente" e entende melhor
VOZES = {
    "A": {"pm_alex": 1.0},
    "B": {"pm_alex": 0.8, "bm_george": 0.2},   # era 65/35: sotaque britânico demais
    "C": {"pm_santa": 1.0},
}


def efeito_ia(a, sr):
    """Pensado para o alto-falante do celular no guidão (2ª versão, a pedido
    do dono): sem reforço de grave (o celular não toca e embola), presença
    forte (clareza no vento), "IA" bem sutil e compressão (sílaba fraca não
    some na rua)."""
    a = np.asarray(a, dtype=np.float64)
    fator = 0.96  # reamostrar = ~meio semitom mais grave
    a = np.interp(np.arange(int(len(a) / fator)) * fator, np.arange(len(a)), a)
    espectro = np.fft.rfft(a)
    f = np.fft.rfftfreq(len(a), 1.0 / sr)
    ganho = 1 / (1 + (150 / np.maximum(f, 1)) ** 4)            # grave que o celular não toca
    ganho *= 1 + 0.75 * np.exp(-((f - 2800) / 1300) ** 2)      # presença (clareza)
    ganho *= 1 + 0.25 * np.exp(-((f - 6000) / 1500) ** 2)      # brilho leve
    ganho *= 1 / (1 + (f / 11000) ** 4)                         # tira chiado
    a = np.fft.irfft(espectro * ganho, len(a))
    saida = a.copy()
    for ms, g in ((11, 0.10), (23, 0.07), (37, 0.04)):         # sala pequena, discreta
        d = int(sr * ms / 1000)
        saida[d:] += g * a[:-d]
    t = np.arange(len(saida)) / sr
    atraso = (0.006 + 0.0015 * np.sin(2 * np.pi * 0.8 * t)) * sr
    saida = saida + 0.07 * np.interp(np.arange(len(saida)) - atraso, np.arange(len(saida)),
                                     saida, left=0)            # assinatura "digital" leve
    x = saida / (np.max(np.abs(saida)) or 1.0)
    return np.tanh(2.2 * x) / np.tanh(2.2)                      # compressão suave


def aparar(a, sr, folga_s=0.03):
    ativo = np.where(np.abs(a) > np.max(np.abs(a)) * 0.02)[0]
    if not len(ativo):
        return a
    folga = int(sr * folga_s)
    return a[max(0, ativo[0] - folga):ativo[-1] + folga]


def reamostrar(a, de, para):
    n = int(round(len(a) * para / de))
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a)


def nivelar(a, rms_alvo=0.16, pico_max=0.97):
    """Todas as falas no mesmo volume percebido, sem estourar."""
    rms = np.sqrt(np.mean(a ** 2)) or 1.0
    a = a * (rms_alvo / rms)
    pico = np.max(np.abs(a))
    return a * (pico_max / pico) if pico > pico_max else a


def gerar_fala(k, estilo, texto):
    audio, sr = k.create(texto, voice=estilo, speed=VELOCIDADE, lang="pt-br")
    return nivelar(reamostrar(aparar(efeito_ia(audio, sr), sr), sr, TAXA))


def amostras(k, pasta):
    """Uma amostra por voz, com frases montadas igual ao app (pedaços + respiro)."""
    frases = [["senhor", "em_200", "vire_direita"], ["senhor", "em_150", "subida_8"],
              ["recalculando"], ["senhor", "chegou"]]
    respiro, pausa = np.zeros(int(TAXA * 0.09)), np.zeros(int(TAXA * 0.5))
    for letra, mistura in VOZES.items():
        estilo = sum(peso * k.get_voice_style(nome) for nome, peso in mistura.items())
        partes = []
        for frase in frases:
            pedacos = [gerar_fala(k, estilo, FALAS[c]) for c in frase]
            for n, p in enumerate(pedacos):
                partes += [p, respiro] if n < len(pedacos) - 1 else [p, pausa]
        caminho = os.path.join(pasta, "voz_%s_nova.wav" % letra)
        sf.write(caminho, np.concatenate(partes).astype(np.float32), TAXA, subtype="PCM_16")
        print("amostra", caminho)


def main():
    letra = (sys.argv[1] if len(sys.argv) > 1 else "B").upper()
    k = Kokoro(os.path.join(PASTA_KOKORO, "kokoro-v1.0.onnx"),
               os.path.join(PASTA_KOKORO, "voices-v1.0.bin"))
    if letra == "AMOSTRAS":
        amostras(k, sys.argv[2])
        return
    estilo = sum(peso * k.get_voice_style(nome) for nome, peso in VOZES[letra].items())
    os.makedirs(SAIDA, exist_ok=True)
    for velho in os.listdir(SAIDA):
        if velho.endswith(".wav") and velho[:-4] not in FALAS:
            os.remove(os.path.join(SAIDA, velho))
    total = 0.0
    for chave, texto in FALAS.items():
        audio = gerar_fala(k, estilo, texto)
        sf.write(os.path.join(SAIDA, chave + ".wav"), audio.astype(np.float32), TAXA,
                 subtype="PCM_16")
        total += len(audio) / TAXA
    tamanho = sum(os.path.getsize(os.path.join(SAIDA, n)) for n in os.listdir(SAIDA))
    print("voz %s: %d falas, %.0f s, %.1f MB" % (letra, len(FALAS), total, tamanho / 1e6))


if __name__ == "__main__":
    main()
