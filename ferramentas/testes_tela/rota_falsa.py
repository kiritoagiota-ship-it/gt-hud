"""Rotas de mentira, para os testes de tela que NÃO são sobre o servidor de rotas.

Dois testes (o do recálculo e o do "Abrir com" durante a rota) pediam a rota de verdade
ao servidor gratuito da internet e falhavam quando ele demorava: um teste que oscila pode
esconder um defeito real (13/10/2026). Com `instalar()`, a rota sai na hora, sempre igual:
um "L" da origem ao destino (segue na mesma longitude e depois vira), com as manobras
"em frente", a curva e a chegada.

Uso, no começo do teste (depois de `import caminhos`):
    import rota_falsa
    rota_falsa.instalar()
"""
import math

import rota as rotas
import rota_tomtom

PASSO_M = 20.0
VELOCIDADE_KMH = 22.0
_M_POR_GRAU = 111320.0


def _linha(a, b):
    """Pontos de `a` até `b` (os dois incluídos), um a cada PASSO_M."""
    k = math.cos(math.radians(a[0]))
    metros = math.hypot((b[0] - a[0]) * _M_POR_GRAU, (b[1] - a[1]) * _M_POR_GRAU * k)
    n = max(1, int(round(metros / PASSO_M)))
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]


def rota_em_l(origem, destino, nome="", perfil="rapida"):
    canto = (destino[0], origem[1])
    primeira = _linha(origem, canto)
    pontos = primeira + _linha(canto, destino)[1:]
    para_o_norte, para_o_leste = destino[0] >= origem[0], destino[1] >= origem[1]
    curva = "direita" if para_o_norte == para_o_leste else "esquerda"
    manobras = [{"acao": "em_frente", "indice": 0, "texto": "", "ruas": "Rua de Teste", "saida": None},
                {"acao": curva, "indice": len(primeira) - 1, "texto": "", "ruas": "Avenida de Teste", "saida": None},
                {"acao": "chegada", "indice": len(pontos) - 1, "texto": "", "ruas": "", "saida": None}]
    total = sum(rotas.distancia_m(p, q) for p, q in zip(pontos, pontos[1:]))
    rota = rotas.Rota(pontos, manobras, [], total / (VELOCIDADE_KMH / 3.6), nome)
    rota.perfil = perfil
    rota.movimentada, rota.estresse = 0.0, 0.0      # (já "medida": ninguém vai à internet por ela)
    return rota


def instalar():
    """Troca os pedidos à internet do módulo de rotas pelas rotas de mentira."""
    def principal(origem, destino, rumo, destino_nome, perfil, alternativas=0, evitar=()):
        rota = rota_em_l(origem, destino, destino_nome, perfil)
        return [rota] if alternativas else rota
    rotas._pedir_principal = principal
    rotas._pedir_reserva = lambda origem, destino, destino_nome: rota_em_l(origem, destino, destino_nome)
    rotas.medir_movimento = lambda rota: rota.movimentada
    rotas.elevacao_de = lambda pontos, enviar=None: []
    rota_tomtom.pedir = lambda *a, **k: None
    rota_tomtom.conferir = lambda *a, **k: None
