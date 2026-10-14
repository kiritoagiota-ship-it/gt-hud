"""Por que o app fechou da última vez, segundo o Android (java/.../Saidas.java).

Uma queda nativa (dentro da placa de vídeo, por exemplo) não deixa rastro no Python. O Android
guarda o motivo de cada saída do app e, para uma queda nativa, o laudo ("tombstone", em
protobuf): o sinal, a biblioteca e a função onde quebrou, e as últimas linhas do logcat.
Aqui as saídas novas (desde a última abertura) viram texto para o diagnóstico.

Formato do laudo: tombstone.proto do Android (system/core/debuggerd/proto). Só os campos
usados aqui são lidos; o resto é pulado.
"""
import os
import time

MOTIVOS = {
    0: "desconhecido", 1: "o app se encerrou", 2: "morto por um sinal", 3: "falta de memória",
    4: "erro do Java", 5: "QUEDA NATIVA", 6: "travou (ANR)", 7: "falha ao iniciar",
    8: "mudança de permissão", 9: "uso excessivo de recursos", 10: "fechado pelo dono",
    11: "parado pelo dono", 12: "dependência morreu", 13: "outro", 14: "congelado",
    15: "mudança no pacote", 16: "app atualizado",
}
QUEDAS = (2, 4, 5, 6, 9, 13)
LINHAS_LOG = 30       # últimas linhas do logcat que vêm no laudo
QUADROS = 24          # quadros da pilha da thread que caiu


# --- protobuf mínimo ---------------------------------------------------------------------------
def _varint(b, i):
    v = s = 0
    while True:
        c = b[i]
        i += 1
        v |= (c & 0x7F) << s
        if c < 0x80:
            return v, i
        s += 7


def _campos(b):
    """[(número, valor)]; valor = int (varint/fixo) ou bytes (comprimento)."""
    out, i, n = [], 0, len(b)
    while i < n:
        chave, i = _varint(b, i)
        num, tipo = chave >> 3, chave & 7
        if tipo == 0:
            v, i = _varint(b, i)
        elif tipo == 1:
            v, i = int.from_bytes(b[i:i + 8], "little"), i + 8
        elif tipo == 2:
            tam, i = _varint(b, i)
            v, i = bytes(b[i:i + tam]), i + tam
        elif tipo == 5:
            v, i = int.from_bytes(b[i:i + 4], "little"), i + 4
        else:
            raise ValueError("tipo %d" % tipo)
        out.append((num, v))
    return out


def _um(campos, num, padrao=None):
    for n, v in campos:
        if n == num:
            return v
    return padrao


def _todos(campos, num):
    return [v for n, v in campos if n == num]


def _txt(v):
    return v.decode("utf-8", "replace") if isinstance(v, bytes) else ("" if v is None else str(v))


def ler_laudo(dados):
    """Texto curto do laudo: sinal, causa, mensagem de abort, a pilha da thread que caiu e o
    fim do logcat. Se o formato não for o esperado, as palavras legíveis do arquivo."""
    try:
        t = _campos(dados)
        linhas = []
        tid = _um(t, 6, 0)
        sinal = _um(t, 10)
        if sinal:
            s = _campos(sinal)
            linhas.append("sinal: %s (%s)%s" % (_txt(_um(s, 2, b"?")), _txt(_um(s, 4, b"")),
                                                " no endereço 0x%x" % _um(s, 9, 0) if _um(s, 8, 0) else ""))
        aborto = _txt(_um(t, 14, b""))
        if aborto:
            linhas.append("abort: " + aborto[:300])
        for c in _todos(t, 15):
            linhas.append("causa: " + _txt(_um(_campos(c), 1, b"")))
        cmd = " ".join(_txt(v) for v in _todos(t, 9))
        if cmd:
            linhas.append("processo: " + cmd)
        for entrada in _todos(t, 16):                       # map<uint32, Thread>
            e = _campos(entrada)
            th = _campos(_um(e, 2, b""))
            if _um(th, 1, -1) != tid:
                continue
            linhas.append("thread que caiu: %s" % _txt(_um(th, 2, b"?")))
            for nota in _todos(th, 7):
                linhas.append("  nota: " + _txt(nota))
            for k, q in enumerate(_todos(th, 4)[:QUADROS]):
                f = _campos(q)
                func = _txt(_um(f, 4, b""))
                arq = _txt(_um(f, 6, b"")).rsplit("/", 1)[-1]
                linhas.append("  #%02d %s%s" % (k, arq or "?", (" (%s+%d)" % (func, _um(f, 5, 0))) if func else ""))
        logs = []
        for buf in _todos(t, 18):
            for m in _todos(_campos(buf), 2):
                mm = _campos(m)
                logs.append("%s %s: %s" % (_txt(_um(mm, 1, b""))[-12:], _txt(_um(mm, 5, b"")),
                                           _txt(_um(mm, 6, b"")).strip()[:220]))
        if logs:
            linhas.append("logcat (fim):")
            linhas.extend("  " + l for l in logs[-LINHAS_LOG:])
        if linhas:
            return "\n".join(linhas)
    except Exception:
        pass
    return _palavras(dados)


def _palavras(dados, minimo=6, maximo=80):
    """Plano B: os trechos legíveis do arquivo (nomes de biblioteca e de função aparecem assim)."""
    achados, atual = [], bytearray()
    for c in bytes(dados[:2_000_000]):
        if 32 <= c < 127:
            atual.append(c)
            continue
        if len(atual) >= minimo:
            achados.append(atual.decode("ascii"))
        atual = bytearray()
    vistos, saida = set(), []
    for p in achados:
        if p not in vistos:
            vistos.add(p)
            saida.append(p)
    return "palavras do laudo: " + " | ".join(saida[:maximo])


# --- as saídas novas -------------------------------------------------------------------------------
def resumir(texto, caminho_laudo, ja_visto_ms):
    """texto = Saidas.ultimas(); devolve (linhas para o diagnóstico, hora_ms mais nova)."""
    linhas = texto.strip().split("\n") if texto else []
    if not linhas or not linhas[0].startswith("laudo="):
        return [], ja_visto_ms
    try:
        linha_laudo = int(linhas[0][6:])
    except ValueError:
        linha_laudo = -1
    saidas, mais_nova = [], ja_visto_ms
    for n, l in enumerate(linhas[1:]):
        partes = l.split("|", 4)
        if len(partes) < 5 or not partes[0].isdigit():
            if l:
                saidas.append("(%s)" % l)
            continue
        hora, motivo, status, processo, desc = int(partes[0]), int(partes[1]), partes[2], partes[3], partes[4]
        mais_nova = max(mais_nova, hora)
        if hora <= ja_visto_ms:
            continue
        quando = time.strftime("%d/%m %H:%M:%S", time.localtime(hora / 1000.0))
        saidas.append("%s %s%s [%s]%s" % (
            quando, "!!! " if motivo in QUEDAS else "", MOTIVOS.get(motivo, "motivo %d" % motivo),
            processo, (" status %s" % status if status not in ("0", "") else "") + (": " + desc if desc else "")))
        if n == linha_laudo and motivo in QUEDAS:
            try:
                with open(caminho_laudo, "rb") as f:
                    dados = f.read()
                # travamento (ANR) vem em texto; queda nativa, em protobuf
                saidas.append(dados[:4000].decode("utf-8", "replace") if motivo == 6 else ler_laudo(dados))
            except OSError:
                pass
    return saidas, mais_nova


def anotar_saidas(pasta):
    """Na abertura: escreve no diagnóstico por que o app fechou desde a última vez (só Android)."""
    try:
        from jnius import autoclass
        atividade = autoclass("org.kivy.android.PythonActivity").mActivity
        caminho_laudo = os.path.join(pasta, "laudo.pb")
        texto = autoclass("org.kirito.gthud.Saidas").ultimas(atividade, 6, caminho_laudo)
    except Exception:
        return
    marca = os.path.join(pasta, "ultima_saida_vista.txt")
    try:
        with open(marca, encoding="utf-8") as f:
            visto = int(f.read().strip() or 0)
    except (OSError, ValueError):
        visto = 0
    saidas, mais_nova = resumir(str(texto), caminho_laudo, visto)
    try:
        os.remove(caminho_laudo)
    except OSError:
        pass
    if saidas:
        print("[saída] por que o app fechou antes (segundo o Android):\n" + "\n".join(saidas), flush=True)
    try:
        with open(marca, "w", encoding="utf-8") as f:
            f.write(str(mais_nova))
    except OSError:
        pass
