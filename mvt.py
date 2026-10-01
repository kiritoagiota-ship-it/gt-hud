"""Leitor mínimo de "Mapbox Vector Tile" (o formato dos tiles do
OpenFreeMap), em Python puro: não tem biblioteca de protobuf no APK.

ler(dados) -> {camada: (extent, [(tipo, propriedades, partes), ...])}
  tipo: 1 ponto, 2 linha, 3 polígono
  partes: listas de (x, y) em unidades do tile (0..extent, Y para baixo)
"""
import gzip
import struct


def _varint(b, i):
    resultado = deslocamento = 0
    while True:
        x = b[i]
        i += 1
        resultado |= (x & 0x7F) << deslocamento
        deslocamento += 7
        if x < 0x80:
            return resultado, i


def _campos(b):
    i, n = 0, len(b)
    while i < n:
        chave, i = _varint(b, i)
        campo, tipo = chave >> 3, chave & 7
        if tipo == 0:
            valor, i = _varint(b, i)
        elif tipo == 2:
            tamanho, i = _varint(b, i)
            valor = b[i:i + tamanho]
            i += tamanho
        elif tipo == 5:
            valor = b[i:i + 4]
            i += 4
        elif tipo == 1:
            valor = b[i:i + 8]
            i += 8
        else:
            raise ValueError("tipo protobuf desconhecido: %d" % tipo)
        yield campo, valor


def _empacotados(b):
    i, saida = 0, []
    while i < len(b):
        v, i = _varint(b, i)
        saida.append(v)
    return saida


def _valor(b):
    for campo, v in _campos(b):
        if campo == 1:
            return v.decode("utf-8", "replace")
        if campo == 2:
            return struct.unpack("<f", v)[0]
        if campo == 3:
            return struct.unpack("<d", v)[0]
        if campo in (4, 5):
            return v
        if campo == 6:
            return (v >> 1) ^ -(v & 1)
        if campo == 7:
            return bool(v)
    return None


def _geometria(cmds):
    partes, atual, x, y, i = [], [], 0, 0, 0
    while i < len(cmds):
        c = cmds[i]
        i += 1
        cid, cont = c & 7, c >> 3
        if cid in (1, 2):  # MoveTo / LineTo
            for _ in range(cont):
                dx, dy = cmds[i], cmds[i + 1]
                i += 2
                x += (dx >> 1) ^ -(dx & 1)
                y += (dy >> 1) ^ -(dy & 1)
                if cid == 1 and atual:
                    partes.append(atual)
                    atual = []
                atual.append((x, y))
        elif cid == 7 and atual:  # ClosePath
            atual.append(atual[0])
    if atual:
        partes.append(atual)
    return partes


def ler(dados, camadas_desejadas=None):
    if dados[:2] == b"\x1f\x8b":
        dados = gzip.decompress(dados)
    camadas = {}
    for campo, v in _campos(dados):
        if campo != 3:
            continue
        nome, extent, chaves, valores, feicoes = None, 4096, [], [], []
        for c2, v2 in _campos(v):
            if c2 == 1:
                nome = v2.decode()
            elif c2 == 3:
                chaves.append(v2.decode())
            elif c2 == 4:
                valores.append(_valor(v2))
            elif c2 == 5:
                extent = v2
            elif c2 == 2:
                feicoes.append(v2)
        if camadas_desejadas is not None and nome not in camadas_desejadas:
            continue
        lista = []
        for f in feicoes:
            tags, tipo, geo = [], 0, []
            for c3, v3 in _campos(f):
                if c3 == 2:
                    tags = _empacotados(v3)
                elif c3 == 3:
                    tipo = v3
                elif c3 == 4:
                    geo = _empacotados(v3)
            props = {chaves[tags[k]]: valores[tags[k + 1]] for k in range(0, len(tags) - 1, 2)}
            lista.append((tipo, props, _geometria(geo)))
        camadas[nome] = (extent, lista)
    return camadas
