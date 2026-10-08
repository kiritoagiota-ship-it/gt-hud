"""Grava as falas do assistente (audio/voz/<chave>.wav) com uma voz da ElevenLabs
(pedido do dono em 08/10/2026: ele tem conta lá e quer a voz dela no app).

Roda no GitHub (.github/workflows/voz-elevenlabs.yml), não no PC: a chave da
ElevenLabs é do dono e fica só no segredo ELEVENLABS_KEY do repositório. Aqui
ela é lida da variável de ambiente e nunca é escrita em lugar nenhum.

    ELEVENLABS_KEY=... python ferramentas/gerar_voz_elevenlabs.py <voice_id> [modelo] [estabilidade] [efeito] [velocidade]

O que faz:
- pede cada fala de falas.py (93 falas, ~2.800 caracteres: cabe com folga nos
  10.000 do plano gratuito) no tom sério de assistente;
- as falas são PEDAÇOS de frase ("Em duzentos metros," + "vire à direita.") que
  o app emenda: cada pedido leva o texto vizinho (previous_text/next_text) para
  a entonação continuar de um pedaço para o outro;
- o plano gratuito só entrega MP3: o ffmpeg converte para WAV (24 kHz, mono),
  e daí vale o mesmo acabamento da voz antiga (aparar o silêncio, pontas
  suaves, todas no mesmo volume);
- só troca as gravações do app se TODAS derem certo (grava numa pasta
  provisória primeiro);
- as gravações LIMPAS ficam em ferramentas/voz_base/ (não vão para o APK) e as do
  app (audio/voz) saem delas com o efeito e a velocidade pedidos
  (ferramentas/efeito_voz.py): trocar o efeito depois não gasta crédito.

Feito pela documentação (elevenlabs.io/docs/api-reference/text-to-speech/convert);
a primeira gravação de verdade é a que o dono disparar.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import caminhos  # noqa: E402,F401  (as pastas do código no caminho de busca)

from falas import FALAS  # noqa: E402

URL = "https://api.elevenlabs.io/v1/text-to-speech/%s?output_format=mp3_44100_128"
SAIDA = os.path.join(RAIZ, "ferramentas", "voz_base")   # as gravações limpas (as do app saem delas: efeito_voz.py)
SOBRE = os.path.join(SAIDA, "voz.json")
TAXA = 24000
MODELO = "eleven_multilingual_v2"
LIMITE_CARACTERES = 6000                     # trava: nunca gasta mais que isso dos créditos numa gravação
RMS_ALVO, PICO_MAX = 0.16, 0.97


def vizinhos(chave):
    """(texto antes, texto depois) para a entonação do pedaço: o que costuma vir
    antes e depois dele numa frase do app."""
    if chave == "senhor":
        return "", "em duzentos metros, vire à direita."
    if chave.startswith("em_"):
        return "Senhor,", "vire à direita."
    if chave == "logo_depois":
        return "Vire à direita.", "vire à esquerda."
    if chave.startswith(("vire_", "levemente_", "acentuada_", "retorno", "em_frente", "mantenha_", "saida_",
                         "rotatoria", "sair_rotatoria", "chegara_destino", "destino_", "subida_", "descida_")):
        return "Senhor, em duzentos metros,", ""
    if chave in ("chegou", "gps_perdido"):
        return "Senhor,", ""
    return "", ""


def pedir(chave_api, voz, texto, antes="", depois="", modelo=MODELO, estabilidade=0.7, abrir=None):
    """Os bytes do MP3 da fala. Levanta RuntimeError com um texto claro se a ElevenLabs recusar."""
    corpo = {"text": texto, "model_id": modelo,
             "voice_settings": {"stability": estabilidade, "similarity_boost": 0.8, "style": 0.0,
                                "use_speaker_boost": True, "speed": 1.0}}   # (a velocidade é do efeito_voz.py)
    if antes:
        corpo["previous_text"] = antes
    if depois:
        corpo["next_text"] = depois
    pedido = urllib.request.Request(URL % voz, data=json.dumps(corpo).encode("utf-8"), method="POST",
                                    headers={"xi-api-key": chave_api, "Content-Type": "application/json",
                                             "Accept": "audio/mpeg"})
    try:
        with (abrir or urllib.request.urlopen)(pedido, timeout=60) as resposta:
            return resposta.read()
    except urllib.error.HTTPError as e:
        detalhe = ""
        try:
            detalhe = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        motivos = {401: "a chave da ElevenLabs foi recusada (confira o segredo ELEVENLABS_KEY)",
                   404: "essa voz não existe na sua conta (confira o Voice ID)",
                   422: "a ElevenLabs não aceitou o pedido",
                   429: "pedidos demais ou créditos esgotados"}
        raise RuntimeError("%s [erro %d] %s" % (motivos.get(e.code, "a ElevenLabs respondeu com erro"), e.code, detalhe))


def mp3_para_wav(mp3, pasta, nome):
    """MP3 -> WAV 24 kHz mono 16 bits (ffmpeg). Devolve o caminho do WAV."""
    entrada, saida = os.path.join(pasta, nome + ".mp3"), os.path.join(pasta, nome + ".cru.wav")
    with open(entrada, "wb") as f:
        f.write(mp3)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", entrada, "-ac", "1", "-ar", str(TAXA),
                    "-sample_fmt", "s16", saida], check=True)
    os.remove(entrada)
    return saida


def acabamento(caminho_cru, caminho_final):
    """Apara o silêncio, suaviza as pontas e deixa no volume das outras (igual à voz antiga)."""
    import numpy as np
    with wave.open(caminho_cru, "rb") as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
    ativo = np.where(np.abs(a) > np.max(np.abs(a)) * 0.02)[0]
    if not len(ativo):
        raise RuntimeError("gravação muda")
    folga = int(TAXA * 0.03)
    a = a[max(0, ativo[0] - folga):ativo[-1] + folga]
    n, m = min(len(a), int(TAXA * 0.012)), min(len(a), int(TAXA * 0.03))
    a[:n] *= np.linspace(0.0, 1.0, n)
    a[len(a) - m:] *= np.linspace(1.0, 0.0, m)
    a = a * (RMS_ALVO / (np.sqrt(np.mean(a ** 2)) or 1.0))
    joelho = 0.70                                  # pico acima do teto: arredonda só a ponta
    modulo = np.abs(a)
    alto = modulo > joelho
    a[alto] = np.sign(a[alto]) * (joelho + (PICO_MAX - joelho) * np.tanh((modulo[alto] - joelho) / (PICO_MAX - joelho)))
    with wave.open(caminho_final, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes((a * 32767).astype("<i2").tobytes())
    os.remove(caminho_cru)
    return len(a) / float(TAXA)


def main():
    chave_api = os.environ.get("ELEVENLABS_KEY", "").strip()
    if not chave_api:
        sys.exit("Falta o segredo ELEVENLABS_KEY (GitHub: Settings > Secrets and variables > Actions).")
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.exit("Falta o Voice ID da voz escolhida.")
    voz = sys.argv[1].strip()
    modelo = (sys.argv[2].strip() if len(sys.argv) > 2 else "") or MODELO
    estabilidade = float(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].strip() else 0.7
    efeito = (sys.argv[4].strip().lower() if len(sys.argv) > 4 else "") or "nenhum"
    velocidade = float(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5].strip() else 1.0
    import efeito_voz
    if efeito not in efeito_voz.EFEITOS:
        sys.exit("efeito desconhecido: %s" % efeito)
    caracteres = sum(len(t) for t in FALAS.values())
    print("%d falas, %d caracteres (voz %s, modelo %s, estabilidade %.2f)" % (len(FALAS), caracteres, voz, modelo, estabilidade))
    if caracteres > LIMITE_CARACTERES:
        sys.exit("As falas somam %d caracteres: acima da trava de %d." % (caracteres, LIMITE_CARACTERES))
    # MODO TESTE (pedido do dono, 08/10/2026, depois de duas vozes recusadas): antes de tudo,
    # pede só a menor fala. A ElevenLabs recusa aqui (voz da Biblioteca no plano grátis, voz
    # que não existe, chave errada) gastando no máximo esses poucos caracteres.
    menor = min(FALAS, key=lambda c: len(FALAS[c]))
    try:
        pedir(chave_api, voz, FALAS[menor], *vizinhos(menor), modelo=modelo, estabilidade=estabilidade)
    except RuntimeError as e:
        sys.exit("TESTE DA VOZ: recusada (gasto: no máximo %d caracteres). %s\nNada foi trocado no app."
                 % (len(FALAS[menor]), e))
    print("TESTE DA VOZ: aceita ('%s', %d caracteres). Gravando as %d falas..."
          % (FALAS[menor], len(FALAS[menor]), len(FALAS)), flush=True)
    pasta = tempfile.mkdtemp(prefix="voz_")
    total = 0.0
    try:
        for n, (chave, texto) in enumerate(FALAS.items(), 1):
            antes, depois = vizinhos(chave)
            for tentativa in range(3):
                try:
                    mp3 = pedir(chave_api, voz, texto, antes, depois, modelo, estabilidade)
                    break
                except RuntimeError as e:
                    if "[erro 429]" in str(e) and tentativa < 2:
                        time.sleep(8 * (tentativa + 1))     # pedidos demais: espera e tenta de novo
                        continue
                    sys.exit("Parei na fala %d (%s): %s\nNada foi trocado no app." % (n, chave, e))
            total += acabamento(mp3_para_wav(mp3, pasta, chave), os.path.join(pasta, chave + ".wav"))
            print("%3d/%d %s" % (n, len(FALAS), chave), flush=True)
            time.sleep(0.4)
        # todas deram certo: troca as gravações do app
        os.makedirs(SAIDA, exist_ok=True)
        for velho in os.listdir(SAIDA):
            if velho.endswith(".wav"):
                os.remove(os.path.join(SAIDA, velho))
        for chave in FALAS:
            shutil.move(os.path.join(pasta, chave + ".wav"), os.path.join(SAIDA, chave + ".wav"))
        with open(SOBRE, "w", encoding="utf-8") as f:
            json.dump({"origem": "elevenlabs", "voz": voz, "modelo": modelo, "feita_em": time.strftime("%Y%m%d%H%M%S")}, f)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    print("pronto: %d falas, %.0f s de áudio, %d caracteres gastos" % (len(FALAS), total, caracteres))
    # as do app: as limpas com o efeito e a velocidade pedidos
    sys.argv = [sys.argv[0], efeito, str(velocidade)]
    efeito_voz.main()


if __name__ == "__main__":
    main()
