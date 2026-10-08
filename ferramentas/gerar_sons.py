"""Gera os sons de aviso do app (sons/<nome>.wav), no estilo HUD: tons curtos e
limpos, pensados para o alto-falante do celular no guidão (pedido do dono em
07/10/2026: "melhore a qualidade sonora e efeitos do app").

    python ferramentas/gerar_sons.py

Só precisa do numpy. Tudo é sintetizado aqui (nenhum som de terceiros): cada
nota é uma senoide com dois harmônicos fracos, ataque de 4 ms (sem estalo) e
queda suave. Faixa de 600 a 2.000 Hz: é onde o alto-falante pequeno toca bem
e o ouvido separa do barulho do vento. Curtos de propósito (0,1 a 0,6 s): a
voz vem logo depois e não pode ser atropelada.
"""
import os
import wave

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(RAIZ, "audio", "sons")
TAXA = 44100
PICO = 0.80           # folga para não distorcer no celular


def nota(freq, dur, queda=6.0, brilho=0.22, ate=None):
    """Uma nota; `ate` = frequência final (a nota desliza de freq até ela)."""
    n = int(TAXA * dur)
    t = np.arange(n) / TAXA
    f = np.full(n, float(freq)) if ate is None else np.linspace(freq, ate, n)
    fase = 2 * np.pi * np.cumsum(f) / TAXA
    onda = np.sin(fase) + brilho * np.sin(2 * fase) + 0.5 * brilho * np.sin(3 * fase)
    envelope = np.minimum(1.0, t / 0.004) * np.exp(-queda * t / dur)
    envelope *= np.minimum(1.0, (dur - t) / 0.006)          # fim sem estalo
    return onda * envelope


def juntar(*partes):
    """partes: (começo em s, onda). Soma tudo numa faixa só."""
    total = max(int(TAXA * ini) + len(o) for ini, o in partes)
    faixa = np.zeros(total)
    for ini, o in partes:
        i = int(TAXA * ini)
        faixa[i:i + len(o)] += o
    return faixa


def eco(a, atraso=0.045, ganho=0.22):
    """Um eco curtinho: dá o ar "digital" sem embolar."""
    d = int(TAXA * atraso)
    saida = np.concatenate([a, np.zeros(d * 2)])
    saida[d:d + len(a)] += ganho * a
    saida[2 * d:2 * d + len(a)] += ganho * ganho * a
    return saida


SONS = {
    # antes de uma curva: duas notas subindo ("atenção, vem instrução")
    "curva": lambda: eco(juntar((0.0, nota(880, 0.09)), (0.085, nota(1320, 0.14, queda=5)))),
    # chegou: quatro notas subindo e uma que fica soando
    "chegada": lambda: eco(juntar((0.0, nota(1047, 0.10)), (0.09, nota(1319, 0.10)), (0.18, nota(1568, 0.10)),
                                  (0.27, nota(2093, 0.38, queda=4))), 0.06, 0.25),
    # recalculando: uma nota escorregando para baixo e voltando ("mudei de plano")
    "recalculo": lambda: eco(juntar((0.0, nota(990, 0.13, ate=620, queda=3)), (0.14, nota(740, 0.13, queda=5)))),
    # radar: dois bipes iguais e secos (o único "duro": é o que não pode passar batido)
    "radar": lambda: juntar((0.0, nota(1760, 0.07, queda=2.5, brilho=0.3)), (0.12, nota(1760, 0.09, queda=3, brilho=0.3))),
    # trânsito, avenida, chuva: três notas descendo, macias
    "alerta": lambda: eco(juntar((0.0, nota(1175, 0.09)), (0.09, nota(988, 0.09)), (0.18, nota(784, 0.16, queda=5)))),
    # rota pronta, caminho melhor: duas notas subindo, abertas
    "pronto": lambda: eco(juntar((0.0, nota(784, 0.10)), (0.10, nota(1175, 0.22, queda=4.5))), 0.05, 0.25),
    # semáforo, lombada, subida: um toque só
    "aviso": lambda: eco(nota(1047, 0.10, queda=5)),
    # começou a navegar: sobe deslizando
    "inicio": lambda: eco(juntar((0.0, nota(520, 0.20, ate=1040, queda=2.5)), (0.19, nota(1560, 0.22, queda=5))), 0.05, 0.22),
    # encerrou a rota: desce
    "fim": lambda: eco(juntar((0.0, nota(1047, 0.10)), (0.10, nota(784, 0.10)), (0.20, nota(523, 0.22, queda=4.5)))),
    # toque em botão: um estalinho de vidro
    "toque": lambda: nota(1900, 0.028, queda=3, brilho=0.1) * 0.45,
}


def gravar(nome, onda):
    onda = np.asarray(onda, dtype=np.float64)
    pico = np.max(np.abs(onda)) or 1.0
    escala = PICO / pico if nome != "toque" else PICO * 0.45 / pico   # o toque de botão é bem mais baixo
    dados = (onda * escala * 32767).astype("<i2")
    os.makedirs(SAIDA, exist_ok=True)
    with wave.open(os.path.join(SAIDA, nome + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(dados.tobytes())
    return len(dados) / float(TAXA)


if __name__ == "__main__":
    for nome, fazer in SONS.items():
        print("%-10s %.2f s" % (nome, gravar(nome, fazer())))
