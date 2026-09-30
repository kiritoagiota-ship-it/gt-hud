"""Gera as falas do assistente (voz/<chave>.wav) a partir de falas.py.

Roda no PC com o Kokoro já instalado para o TraveteFocus (fica fora do APK):
  C:\\Users\\kirit\\travetefocus\\ferramentas\\voz\\venv\\Scripts\\python.exe ferramentas\\gerar_voz.py B

A letra escolhe a voz (amostras mandadas ao dono em 30/09/2026):
  A = pm_alex (brasileira)
  B = pm_alex misturada com bm_george (brasileira com timbre britânico)
  C = pm_santa (brasileira)
Voz ORIGINAL no estilo de assistente de IA: não imita a voz real do Jarvis
(ela pertence ao ator/dublador). O "efeito IA" é só numpy: um pouco mais
grave, equalização com corpo e presença, eco curtinho de "capacete" e um
chorus leve.
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
VELOCIDADE = 1.02
VOZES = {
    "A": {"pm_alex": 1.0},
    "B": {"pm_alex": 0.65, "bm_george": 0.35},
    "C": {"pm_santa": 1.0},
}


def efeito_ia(a, sr):
    a = np.asarray(a, dtype=np.float64)
    fator = 0.94  # reamostrar = ~1 semitom mais grave
    a = np.interp(np.arange(int(len(a) / fator)) * fator, np.arange(len(a)), a)
    espectro = np.fft.rfft(a)
    f = np.fft.rfftfreq(len(a), 1.0 / sr)
    ganho = 1 / (1 + (80 / np.maximum(f, 1)) ** 4)             # tira o grave embolado
    ganho *= 1 + 0.35 * np.exp(-((f - 180) / 120) ** 2)        # corpo
    ganho *= 1 + 0.45 * np.exp(-((f - 3000) / 1200) ** 2)      # presença (clareza)
    ganho *= 1 / (1 + (f / 9000) ** 4)                          # tira chiado
    a = np.fft.irfft(espectro * ganho, len(a))
    saida = a.copy()
    for ms, g in ((9, 0.22), (17, 0.15), (29, 0.10), (43, 0.06)):  # "capacete"
        d = int(sr * ms / 1000)
        saida[d:] += g * a[:-d]
    t = np.arange(len(saida)) / sr
    atraso = (0.006 + 0.0015 * np.sin(2 * np.pi * 0.8 * t)) * sr
    saida = saida + 0.18 * np.interp(np.arange(len(saida)) - atraso, np.arange(len(saida)),
                                     saida, left=0)
    return saida


def aparar(a, sr, folga_s=0.03):
    ativo = np.where(np.abs(a) > np.max(np.abs(a)) * 0.02)[0]
    if not len(ativo):
        return a
    folga = int(sr * folga_s)
    return a[max(0, ativo[0] - folga):ativo[-1] + folga]


def reamostrar(a, de, para):
    n = int(round(len(a) * para / de))
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a)


def nivelar(a, rms_alvo=0.12, pico_max=0.95):
    """Todas as falas no mesmo volume percebido, sem estourar."""
    rms = np.sqrt(np.mean(a ** 2)) or 1.0
    a = a * (rms_alvo / rms)
    pico = np.max(np.abs(a))
    return a * (pico_max / pico) if pico > pico_max else a


def main():
    letra = (sys.argv[1] if len(sys.argv) > 1 else "B").upper()
    k = Kokoro(os.path.join(PASTA_KOKORO, "kokoro-v1.0.onnx"),
               os.path.join(PASTA_KOKORO, "voices-v1.0.bin"))
    estilo = sum(peso * k.get_voice_style(nome) for nome, peso in VOZES[letra].items())
    os.makedirs(SAIDA, exist_ok=True)
    for velho in os.listdir(SAIDA):
        if velho.endswith(".wav") and velho[:-4] not in FALAS:
            os.remove(os.path.join(SAIDA, velho))
    total = 0.0
    for chave, texto in FALAS.items():
        audio, sr = k.create(texto, voice=estilo, speed=VELOCIDADE, lang="pt-br")
        audio = nivelar(reamostrar(aparar(efeito_ia(audio, sr), sr), sr, TAXA))
        sf.write(os.path.join(SAIDA, chave + ".wav"), audio.astype(np.float32), TAXA,
                 subtype="PCM_16")
        total += len(audio) / TAXA
    tamanho = sum(os.path.getsize(os.path.join(SAIDA, n)) for n in os.listdir(SAIDA))
    print("voz %s: %d falas, %.0f s, %.1f MB" % (letra, len(FALAS), total, tamanho / 1e6))


if __name__ == "__main__":
    main()
