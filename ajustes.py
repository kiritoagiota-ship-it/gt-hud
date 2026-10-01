"""Configurações do usuário salvas em JSON."""
import json
import os

PADRAO = {
    "limite_kmh": 32,
    "alfa": 0.5,
    "tela_ligada": True,
    "simulador": False,
    "vibrar_limite": True,
    "pausa_auto": True,
    "tela_deitada": False,
    "voz": True,
    "girar_mapa": True,
    "avisar_subidas": True,
    "voz_indice": -1,        # -1 = a voz padrão do motor do celular
    "voz_tom": 0.88,         # abaixo de 1 = mais grave
    "voz_efeito": True,      # tratamento estilo assistente de IA
}


class Ajustes:
    def __init__(self, pasta):
        os.makedirs(pasta, exist_ok=True)
        self.caminho = os.path.join(pasta, "ajustes.json")
        self.dados = dict(PADRAO)
        try:
            with open(self.caminho, "r") as f:
                self.dados.update(json.load(f))
        except (OSError, ValueError):
            pass

    def __getitem__(self, chave):
        return self.dados[chave]

    def __setitem__(self, chave, valor):
        self.dados[chave] = valor
        self.salvar()

    def salvar(self):
        with open(self.caminho, "w") as f:
            json.dump(self.dados, f)
