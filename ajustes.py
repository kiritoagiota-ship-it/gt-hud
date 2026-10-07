"""Configurações do usuário salvas em JSON."""
import json
import os
import threading

PADRAO = {
    "limite_kmh": 32,
    "alfa": 0.5,
    "vel_ajuste": 0,         # % somado ao velocímetro (0 = velocidade real do GPS)
    "alfa_v2": False,        # a "Resposta" antiga em 0,1-0,2 atrasava: volta a 0,5 uma vez
    "firebase": "",          # endereço do banco do dono para a corrida ao vivo (ao_vivo.py)
    "corridas_abertas": [],  # [banco, código, senha] de corrida ao vivo ainda não encerrada no banco
    "atalhos": {},           # {"casa": lugar, "trabalho": lugar}: destinos de um toque na busca
    "rota_preferida": "rapida",   # "rapida" ou "tranquila": a que já vem escolhida na prévia
    "tema": "auto",          # "auto" (claro de dia, escuro à noite), "claro" ou "escuro"
    "ritmo": 1.0,   # tempo real do dono / tempo previsto pelo servidor de rotas (ritmo.py)
    "tela_ligada": True,
    "simulador": False,
    "vibrar_limite": True,
    "pausa_auto": True,
    "tela_deitada": False,
    "voz": True,
    "girar_mapa": True,
    "avisar_subidas": True,
    "avisar_semaforos": True,   # lombada é avisada sempre (segurança)
    "segundo_plano": True,      # rota ativa + app minimizado: continua navegando
    "flutuante_tipo": "painel",  # o que aparece minimizado: "painel" (retângulo com a rota e a
                                 # velocidade) ou "bolha" (pequena, só minutos e km)
    "bolha": True,              # ... com a bolha de km/minutos por cima dos apps
    "voz_indice": -1,        # -1 = automática: a mais grave (masculina) do celular
    "voz_auto": -1,          # índice que a medição achou (-1 = ainda não mediu)
    "voz_auto_nome": "",     # nome dessa voz (se a lista mudar, mede de novo)
    "voz_masculina_v1": False,  # já passou para a voz automática uma vez (pedido do dono)
    "voz_tom": 0.94,         # abaixo de 1 = mais grave
    "voz_efeito": True,      # tratamento estilo assistente de IA
}


class Ajustes:
    def __init__(self, pasta):
        os.makedirs(pasta, exist_ok=True)
        self.caminho = os.path.join(pasta, "ajustes.json")
        self._trava = threading.Lock()
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
        """Grava num arquivo ao lado e troca de uma vez: se o app for morto no
        meio, o arquivo antigo continua inteiro (antes podia ficar pela
        metade e TODOS os ajustes voltavam ao padrão). Com trava: a thread de
        segundo plano também grava (ritmo, corrida ao vivo)."""
        with self._trava:
            temporario = self.caminho + ".tmp"
            try:
                with open(temporario, "w") as f:
                    json.dump(self.dados, f)
                os.replace(temporario, self.caminho)
            except OSError as e:
                print("[ajustes] nao consegui gravar:", e)
