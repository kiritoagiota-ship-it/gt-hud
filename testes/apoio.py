"""Coisas comuns dos testes: rotas de mentira, sem internet."""
import rota as rotas

M_GRAU = 111320.0


def rota_reta(comprimento_m=600, passo_m=10, manobras=None, elevacao=None, tempo_s=120,
              lat0=-16.68, lon0=-49.25):
    """Rota reta para o norte, um ponto a cada passo_m."""
    pontos = [(lat0 + d / M_GRAU, lon0) for d in range(0, comprimento_m + 1, passo_m)]
    if manobras is None:
        manobras = [{"acao": "em_frente", "indice": 0, "texto": "", "ruas": "A", "saida": None},
                    {"acao": "chegada", "indice": len(pontos) - 1, "texto": "", "ruas": "", "saida": None}]
    if elevacao is None:
        elevacao = [800.0] * (comprimento_m // rotas.ELEVACAO_PASSO_M + 1)
    return rotas.Rota(pontos, manobras, elevacao, tempo_s, "Teste")


def manobra(acao, indice, saida=None):
    return {"acao": acao, "indice": indice, "texto": "", "ruas": "Rua %d" % indice, "saida": saida}


class Fala:
    """Guarda o que o assistente falaria: (frase montada, prioridade)."""

    def __init__(self):
        self.ditas = []

    def __call__(self, pedacos, prioridade, texto=None):
        import falas
        self.ditas.append((texto or falas.frase(pedacos), prioridade))

    def textos(self):
        return [t for t, _ in self.ditas]
