"""Onde fica cada parte do código (organizado em pastas em 08/10/2026).

O código foi agrupado por assunto, mas cada arquivo continua sendo chamado pelo
mesmo nome de antes (`import rota`, `import voz`...): este módulo põe as pastas
no caminho de busca do Python. Por isso ele precisa ser o PRIMEIRO import de
quem começa um programa: main.py, os testes (testes/__init__.py) e as
ferramentas.

RAIZ é a pasta do projeto (onde ficam main.py, dados/, chaves.json, versao.json).
"""
import os
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
PASTAS = ("mapa_motor",        # dados do mapa, preparo do desenho, semáforos e radares
          "rotas_e_busca",     # rotas, navegação curva a curva, busca de lugares e endereços
          "transito_e_clima",  # trânsito ao vivo (TomTom) e previsão de chuva
          "audio",             # voz, sons de aviso e as gravações (audio/voz, audio/sons)
          "gps",               # GPS do celular, simulador do PC e o filtro do velocímetro
          "sistema")           # ajustes, banco, viagem, diagnóstico, internet, tema, segundo plano

for _pasta in PASTAS:
    _caminho = os.path.join(RAIZ, _pasta)
    if _caminho not in sys.path:
        sys.path.insert(0, _caminho)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
