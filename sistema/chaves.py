"""Chaves de serviços (ex.: Google Places).

O repositório é PÚBLICO: a chave nunca vai para o código. Ela fica nos
"secrets" do GitHub e o build grava um chaves.json dentro do APK (ver
.github/workflows/build.yml); chaves.json está no .gitignore. Sem o arquivo
(no PC, ou sem o secret), o app usa só os serviços sem conta.
"""
import json
import os

import caminhos

_ARQUIVO = os.path.join(caminhos.RAIZ, "chaves.json")
_cache = None


def chave(nome):
    global _cache
    if _cache is None:
        try:
            with open(_ARQUIVO, encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
    valor = _cache.get(nome) or ""
    return valor.strip() or None
