"""Deixa a voz do assistente mais lenta e com um timbre grave e sombrio, "tipo o
Venom" (pedido do dono em 08/10/2026: "ele tá falando muito rápido, e eu queria
uma voz tipo o Venom").

    python ferramentas/efeito_voz.py forte 0.85      (efeito, velocidade)

Lê as gravações LIMPAS de ferramentas/voz_base/ (as que a ElevenLabs entregou,
guardadas por gerar_voz_elevenlabs.py; não vão para o APK) e grava as do app em
audio/voz/. Pode rodar quantas vezes quiser, com outro efeito ou velocidade:
não gasta crédito nenhum, e o efeito nunca se acumula (parte sempre da limpa).

É um efeito ORIGINAL feito só com contas (numpy): não copia a voz do personagem
nem do ator, só o clima. Como é feito (2ª versão: a 1ª ficou "robotizada demais", disse o dono):
- TOM mais grave SEM mudar a duração além do pedido: a fala é encurtada no tempo
  colando pedacinhos dela mesma onde a onda encaixa (WSOLA, o método usado para
  fala) e a reamostragem estica de volta, descendo o tom. A 1ª versão usava um
  "phase vocoder", que deixa um chiado metálico: era o robô;
- uma SEGUNDA VOZ uma oitava abaixo, só nos graves (abaixo de ~400 Hz), por baixo;
- sem o tremor ("ronco") da 1ª versão, que soava como máquina, e com bem menos
  distorção;
- grave reforçado e um eco curto e escuro;
- a faixa de 2 a 4 kHz (onde moram as consoantes) é preservada: no guidão, com
  vento, entender "vire à esquerda" vale mais que o efeito.

Efeitos: "nenhum" (só a velocidade), "leve", "medio", "forte".
"""
import json
import os
import sys
import time
import wave

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(RAIZ, "ferramentas", "voz_base")
SAIDA = os.path.join(RAIZ, "audio", "voz")
SOBRE = os.path.join(SAIDA, "voz.json")
RMS_ALVO, PICO_MAX = 0.16, 0.97
CLAREZA = 1.6   # quanto do agudo original volta por cima no efeito mais forte (ver aplicar)

# efeito -> (tom da voz principal, volume da voz de baixo, ronco, distorção, grave, eco)
#   tom: 1.0 = igual; 0.75 = uns 5 semitons mais grave
EFEITOS = {
    "nenhum": (1.00, 0.00, 0.00, 0.0, 0.0, 0.00),
    "leve":   (0.90, 0.00, 0.00, 0.4, 0.4, 0.04),
    "medio":  (0.83, 0.25, 0.00, 0.7, 0.7, 0.07),
    "forte":  (0.76, 0.42, 0.00, 1.0, 1.0, 0.10),
}


def esticar(a, fator, quadro=1024, salto=256):
    """Muda a DURAÇÃO (fator > 1 = mais longa) sem mudar o tom (phase vocoder)."""
    if abs(fator - 1.0) < 1e-3 or len(a) < quadro * 2:
        return a.copy()
    janela = np.hanning(quadro)
    a = np.concatenate([np.zeros(quadro), a, np.zeros(quadro)])
    n_quadros = 1 + (len(a) - quadro) // salto
    espectros = np.array([np.fft.rfft(janela * a[i * salto:i * salto + quadro]) for i in range(n_quadros)])
    passos = np.arange(0, n_quadros - 1, 1.0 / fator)          # onde "ler" o som original, em quadros
    avanco = 2.0 * np.pi * salto * np.arange(espectros.shape[1]) / quadro
    fase = np.angle(espectros[0])
    saida = np.zeros(len(passos) * salto + quadro)
    norma = np.zeros_like(saida)
    for k, p in enumerate(passos):
        i = int(p)
        f = p - i
        modulo = (1.0 - f) * np.abs(espectros[i]) + f * np.abs(espectros[i + 1])
        pedaco = np.fft.irfft(modulo * np.exp(1j * fase), quadro) * janela
        saida[k * salto:k * salto + quadro] += pedaco
        norma[k * salto:k * salto + quadro] += janela ** 2
        desvio = np.angle(espectros[i + 1]) - np.angle(espectros[i]) - avanco
        desvio -= 2.0 * np.pi * np.round(desvio / (2.0 * np.pi))
        fase += avanco + desvio
    saida /= np.maximum(norma, 1e-3)
    corte = int(quadro * fator)
    return saida[corte:len(saida) - corte] if len(saida) > 2 * corte + quadro else saida


def wsola(a, fator, sr=24000):
    """Muda a DURAÇÃO da fala (fator > 1 = mais longa) sem mudar o tom, colando janelas
    de 40 ms dela mesma; cada janela é procurada (±10 ms) onde a onda melhor continua a
    anterior. Não mexe na fase do som: não deixa o chiado metálico do phase vocoder."""
    if abs(fator - 1.0) < 1e-3:
        return np.asarray(a, dtype=np.float64).copy()
    quadro = int(sr * 0.040) // 2 * 2
    salto = quadro // 2
    busca = int(sr * 0.010)
    janela = np.hanning(quadro)
    n_saida = int(len(a) * fator)
    a = np.concatenate([np.zeros(busca + quadro), np.asarray(a, dtype=np.float64), np.zeros(busca + 2 * quadro)])
    saida = np.zeros(n_saida + 2 * quadro)
    pos = busca + quadro           # onde a última janela começou no som original
    saida[:quadro] += a[pos:pos + quadro] * janela
    k = 1
    while k * salto + quadro < len(saida):
        ideal = busca + quadro + int(k * salto / fator)      # onde o tempo novo "quer" ler
        if ideal + busca + quadro >= len(a):
            break
        natural = a[pos + salto:pos + salto + quadro]         # a continuação natural da janela anterior
        melhor, melhor_c = ideal, -1e30
        for d in range(-busca, busca + 1, 4):
            c = float(np.dot(natural, a[ideal + d:ideal + d + quadro]))
            if c > melhor_c:
                melhor, melhor_c = ideal + d, c
        pos = melhor
        saida[k * salto:k * salto + quadro] += a[pos:pos + quadro] * janela
        k += 1
    return saida[:n_saida]


def reamostrar(a, fator):
    """Estica o som como uma fita mais lenta: fator > 1 = mais longo E mais grave."""
    n = max(2, int(round(len(a) * fator)))
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a)


def mudar_tom(a, tom, duracao):
    """A fala com o tom multiplicado por `tom` (<1 = mais grave) e a duração por `duracao`."""
    return reamostrar(wsola(a, duracao * tom), 1.0 / tom)


def igualar(a, sr, grave, presenca=0.25):
    espectro = np.fft.rfft(a)
    f = np.fft.rfftfreq(len(a), 1.0 / sr)
    ganho = 1.0 / (1.0 + (70.0 / np.maximum(f, 1.0)) ** 4)               # abaixo de 70 Hz o celular não toca
    ganho *= 1.0 + grave * np.exp(-((f - 190.0) / 110.0) ** 2)            # corpo
    ganho *= 1.0 + presenca * np.exp(-((f - 3000.0) / 1100.0) ** 2)       # consoantes (clareza)
    ganho *= 1.0 / (1.0 + (f / 9000.0) ** 6)
    return np.fft.irfft(espectro * ganho, len(a))


def aplicar(a, sr, efeito="forte", velocidade=0.85):
    """A gravação limpa -> a do app. velocidade 0.85 = 15% mais lenta."""
    tom, baixo, ronco, distorcao, grave, eco = EFEITOS[efeito]
    duracao = 1.0 / velocidade
    a = np.asarray(a, dtype=np.float64)
    voz = mudar_tom(a, tom, duracao)
    if baixo > 0:
        sub = mudar_tom(a, tom / 2.0, duracao)                 # o "monstro": uma oitava abaixo
        n = min(len(voz), len(sub))
        voz, sub = voz[:n], sub[:n]
        t = np.arange(n) / float(sr)
        if ronco > 0:
            sub = sub * (1.0 - ronco + ronco * np.abs(np.sin(2.0 * np.pi * 15.0 * t)))   # treme ~30x por segundo
        # só o grave da voz de baixo: acima de ~400 Hz ela embolaria as palavras
        espectro_sub = np.fft.rfft(sub)
        f_sub = np.fft.rfftfreq(len(sub), 1.0 / sr)
        sub = np.fft.irfft(espectro_sub / (1.0 + (f_sub / 400.0) ** 6), len(sub))
        sub = igualar(sub, sr, grave, presenca=0.0)
        voz = voz + baixo * sub * (np.sqrt(np.mean(voz ** 2)) / (np.sqrt(np.mean(sub ** 2)) or 1.0))
    voz = igualar(voz, sr, grave)
    if tom < 0.999:
        # CLAREZA: descer o tom leva junto as consoantes ("s", "t", "ch"), que ficam abafadas. Por
        # cima da voz grave volta só o agudo (acima de ~2 kHz) da fala original, no tempo novo:
        # o timbre continua de monstro e as palavras continuam nítidas.
        claro = wsola(a, duracao)
        espectro = np.fft.rfft(claro)
        f = np.fft.rfftfreq(len(claro), 1.0 / sr)
        claro = np.fft.irfft(espectro / (1.0 + (2200.0 / np.maximum(f, 1.0)) ** 6), len(claro))
        n = min(len(voz), len(claro))
        voz = voz[:n] + CLAREZA * (1.0 - tom) / 0.28 * claro[:n] * (np.sqrt(np.mean(voz[:n] ** 2)) / (np.sqrt(np.mean(a ** 2)) or 1.0))
    if distorcao > 0:
        x = voz / (np.max(np.abs(voz)) or 1.0)
        voz = np.tanh(distorcao * x) / np.tanh(distorcao)
    if eco > 0:
        saida = voz.copy()
        for ms, g in ((23, eco), (41, eco * 0.6), (67, eco * 0.35)):
            d = int(sr * ms / 1000.0)
            saida[d:] += g * voz[:-d]
        voz = saida
    # pontas suaves e o mesmo volume em todas
    n, m = min(len(voz), int(sr * 0.012)), min(len(voz), int(sr * 0.04))
    voz[:n] *= np.linspace(0.0, 1.0, n)
    voz[len(voz) - m:] *= np.linspace(1.0, 0.0, m)
    voz = voz * (RMS_ALVO / (np.sqrt(np.mean(voz ** 2)) or 1.0))
    joelho = 0.70
    modulo = np.abs(voz)
    alto = modulo > joelho
    voz[alto] = np.sign(voz[alto]) * (joelho + (PICO_MAX - joelho) * np.tanh((modulo[alto] - joelho) / (PICO_MAX - joelho)))
    return voz


def ler(caminho):
    with wave.open(caminho, "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0, w.getframerate()


def gravar(caminho, a, sr):
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(a, -1.0, 1.0) * 32767).astype("<i2").tobytes())


def main():
    efeito = (sys.argv[1] if len(sys.argv) > 1 else "forte").strip().lower() or "forte"
    velocidade = float(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].strip() else 0.85
    if efeito not in EFEITOS:
        sys.exit("efeito desconhecido: %s (use %s)" % (efeito, ", ".join(EFEITOS)))
    if not 0.6 <= velocidade <= 1.2:
        sys.exit("velocidade fora do razoável (0.6 a 1.2): %s" % velocidade)
    nomes = sorted(n for n in os.listdir(BASE) if n.endswith(".wav")) if os.path.isdir(BASE) else []
    if not nomes:
        sys.exit("não há gravações limpas em ferramentas/voz_base (rode a gravação da ElevenLabs primeiro)")
    os.makedirs(SAIDA, exist_ok=True)
    total = 0.0
    for nome in nomes:
        a, sr = ler(os.path.join(BASE, nome))
        b = aplicar(a, sr, efeito, velocidade)
        gravar(os.path.join(SAIDA, nome), b, sr)
        total += len(b) / float(sr)
    for velho in os.listdir(SAIDA):
        if velho.endswith(".wav") and velho not in nomes:
            os.remove(os.path.join(SAIDA, velho))
    sobre = {}
    try:
        with open(os.path.join(BASE, "voz.json"), encoding="utf-8") as f:
            sobre = json.load(f)
    except (OSError, ValueError):
        pass
    sobre.update(efeito=efeito, velocidade=velocidade, feita_em=time.strftime("%Y%m%d%H%M%S"))
    with open(SOBRE, "w", encoding="utf-8") as f:
        json.dump(sobre, f)
    print("efeito %s, velocidade %.2f: %d falas, %.0f s de áudio" % (efeito, velocidade, len(nomes), total))


if __name__ == "__main__":
    main()
