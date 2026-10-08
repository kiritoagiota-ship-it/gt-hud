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

from falas import GRAVADAS as FALAS  # noqa: E402  (o texto da voz gravada: fala como "nós")

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
        return "", "em duzentos metros, viramos à direita."
    if chave.startswith("em_"):
        return "Parceiro,", "viramos à direita."
    if chave == "logo_depois":
        return "Viramos à direita.", "viramos à esquerda."
    if chave.startswith(("vire_", "levemente_", "acentuada_", "retorno", "em_frente", "mantenha_", "saida_",
                         "rotatoria", "sair_rotatoria", "chegara_destino", "destino_", "subida_", "descida_")):
        return "Parceiro, em duzentos metros,", ""
    if chave in ("chegou", "gps_perdido"):
        return "Parceiro,", ""
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
        if "quota_exceeded" in detalhe:
            raise RuntimeError("acabaram os créditos liberados (o limite da própria chave, ou os da conta) [erro %d] %s"
                               % (e.code, detalhe))
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


def _ler_sobre():
    try:
        with open(SOBRE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _gravar_sobre(sobre):
    os.makedirs(SAIDA, exist_ok=True)
    with open(SOBRE, "w", encoding="utf-8") as f:
        json.dump(sobre, f, ensure_ascii=False)


def a_gravar(sobre, voz, modelo, estabilidade):
    """As falas que ainda precisam ser pedidas à ElevenLabs: as que não têm gravação limpa
    com ESTE texto, ESTA voz e ESTE jeito. O resto é reaproveitado (não gasta crédito)."""
    mesma = (sobre.get("voz") == voz and sobre.get("modelo") == modelo
             and abs(float(sobre.get("estabilidade", -1)) - estabilidade) < 1e-6)
    textos = sobre.get("textos", {}) if mesma else {}
    return [c for c in FALAS
            if textos.get(c) != FALAS[c] or not os.path.exists(os.path.join(SAIDA, c + ".wav"))]


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
    sobre = _ler_sobre()
    faltam = a_gravar(sobre, voz, modelo, estabilidade)
    caracteres = sum(len(FALAS[c]) for c in faltam)
    print("%d falas no app; %d já gravadas com este texto e esta voz (reaproveitadas); %d a gravar = %d caracteres"
          % (len(FALAS), len(FALAS) - len(faltam), len(faltam), caracteres), flush=True)
    if caracteres > LIMITE_CARACTERES:
        sys.exit("As falas a gravar somam %d caracteres: acima da trava de %d." % (caracteres, LIMITE_CARACTERES))
    if len(faltam) == len(FALAS) or sobre.get("voz") != voz:
        # voz nova: as gravações da voz antiga não servem mais (nem como reaproveitamento)
        sobre = {"origem": "elevenlabs", "voz": voz, "modelo": modelo, "estabilidade": estabilidade, "textos": {}}
    sobre.update(voz=voz, modelo=modelo, estabilidade=estabilidade)
    sobre.setdefault("textos", {})
    os.makedirs(SAIDA, exist_ok=True)
    pasta = tempfile.mkdtemp(prefix="voz_")
    gastos = 0
    try:
        # Cada fala que dá certo já fica guardada (gravação limpa + o texto dela em voz.json): se
        # algo parar no meio (créditos, internet), a próxima tentativa CONTINUA de onde parou, sem
        # pagar de novo pelo que já foi feito. As gravações do APP (audio/voz) só são refeitas no
        # fim, quando todas existem: o app nunca fica com metade de cada voz.
        for n, chave in enumerate(faltam, 1):
            texto = FALAS[chave]
            antes, depois = vizinhos(chave)
            for tentativa in range(3):
                try:
                    mp3 = pedir(chave_api, voz, texto, antes, depois, modelo, estabilidade)
                    break
                except RuntimeError as e:
                    if "[erro 429]" in str(e) and tentativa < 2:
                        time.sleep(8 * (tentativa + 1))     # pedidos demais: espera e tenta de novo
                        continue
                    sys.exit("Parei na fala %d de %d (%s): %s\nAs %d já gravadas ficaram guardadas (%d caracteres); "
                             "o app continua com a voz de antes." % (n, len(faltam), chave, e, n - 1, gastos))
            acabamento(mp3_para_wav(mp3, pasta, chave), os.path.join(SAIDA, chave + ".wav"))
            sobre["textos"][chave] = texto
            _gravar_sobre(sobre)
            gastos += len(texto)
            print("%3d/%d %s" % (n, len(faltam), chave), flush=True)
            time.sleep(0.4)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    for velho in os.listdir(SAIDA):                      # fala que saiu do app
        if velho.endswith(".wav") and velho[:-4] not in FALAS:
            os.remove(os.path.join(SAIDA, velho))
    sobre["textos"] = {c: t for c, t in sobre["textos"].items() if c in FALAS}
    sobre["feita_em"] = time.strftime("%Y%m%d%H%M%S")
    _gravar_sobre(sobre)
    print("pronto: %d falas gravadas agora, %d caracteres gastos" % (len(faltam), gastos))
    # as do app: as limpas com o efeito e a velocidade pedidos
    sys.argv = [sys.argv[0], efeito, str(velocidade)]
    efeito_voz.main()


if __name__ == "__main__":
    main()
