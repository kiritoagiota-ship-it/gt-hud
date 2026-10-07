"""Testa a PÁGINA do "corrida ao vivo" no PC, sem Firebase de verdade:
sobe o banco de mentira (firebase_falso.py), serve a pasta docs/ e simula
uma corrida pela cidade. Abra o endereço que aparece no navegador.

    python ferramentas/simular_ao_vivo.py [segundos de corrida] [endereço de um banco de verdade]

Com o endereço de um banco de verdade, a corrida de teste vai para ele (e é
encerrada no fim): serve para testar o canal ao vivo, que o banco de mentira
não tem.
"""
import functools
import http.server
import math
import os
import sys
import threading
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_LOG_MODE", "PYTHON")

import ao_vivo  # noqa: E402
import rota as rotas  # noqa: E402
from ferramentas.firebase_falso import servidor  # noqa: E402

PORTA_BANCO, PORTA_PAGINA = 8765, 8766
CODIGO = "corrida-de-teste-no-pc-0001"
# um caminho de ~1,6 km pelo Setor Central de Goiânia
PONTOS = [(-16.6799, -49.2550), (-16.6790, -49.2562), (-16.6772, -49.2568), (-16.6755, -49.2574),
          (-16.6741, -49.2592), (-16.6728, -49.2611), (-16.6712, -49.2619), (-16.6695, -49.2626)]


def main():
    duracao = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    base = ao_vivo.limpar_endereco(sys.argv[2]) if len(sys.argv) > 2 else None
    if base is None:
        servidor(PORTA_BANCO)
        base = "http://127.0.0.1:%d" % PORTA_BANCO
    pagina = http.server.ThreadingHTTPServer(
        ("127.0.0.1", PORTA_PAGINA),
        functools.partial(http.server.SimpleHTTPRequestHandler, directory=os.path.join(RAIZ, "docs")))
    threading.Thread(target=pagina.serve_forever, daemon=True).start()

    rota = rotas.Rota(PONTOS, [], [], 300, "Praça do Trabalhador")
    corrida = ao_vivo.AoVivo(base)
    corrida.codigo = CODIGO + "-" + corrida.codigo[:6]
    corrida.comecar(rota, rota.destino_nome)
    print("Abra: http://127.0.0.1:%d/acompanhar/#%s/%s" % (PORTA_PAGINA, base.split("://", 1)[1], corrida.codigo),
          flush=True)

    inicio = time.time()
    while time.time() - inicio < duracao:
        f = (time.time() - inicio) / duracao
        d = rota.total_m * f
        lat, lon, rumo = rota.ponto_em(d)
        vel = 24 + 6 * math.sin(f * 20)
        corrida.leitura(lat, lon, vel, rumo, rota.total_m - d, rota.tempo_s * (1 - f), d)
        time.sleep(1.0)
    corrida.terminar(chegou=True)
    corrida.esperar_fim()
    print("Chegou. A página deve mostrar o fim. (servidores no ar por mais 60 s)", flush=True)
    time.sleep(60)


if __name__ == "__main__":
    main()
