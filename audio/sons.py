"""Sons de aviso do app (sons/*.wav, feitos por ferramentas/gerar_sons.py):
um toque curto ANTES da fala diz o tipo do aviso sem precisar entender as
palavras (duas notas subindo = vem curva; dois bipes secos = radar...).

Sons.tocar(nome) toca na hora, fora da fila da voz (são curtos: 0,1 a 0,6 s;
a voz gravada começa com 0,3 s de silêncio, então não se atropelam).
som_da_fala(pedaços) diz qual som anuncia cada fala.
"""
import os

from kivy.core.audio import SoundLoader

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sons")
VOLUMES = {"desligado": 0.0, "baixo": 0.35, "medio": 0.65, "alto": 1.0}
NOMES_VOLUME = (("desligado", "Desligado"), ("baixo", "Baixo"), ("medio", "Médio"), ("alto", "Alto"))

# fala (o 1º pedaço que constar aqui decide) -> som
_DA_FALA = {
    "chegou": "chegada", "recalculando": "recalculo", "radar": "radar",
    "incidente": "alerta", "avenida": "alerta", "chuva": "alerta", "gps_perdido": "alerta", "sem_internet": "alerta",
    "sem_rota": "alerta",
    "rota_calculada": "inicio", "caminho_melhor": "pronto", "rota_trocada": "pronto", "gps_ok": "pronto",
    "semaforo": "aviso", "lombada": "aviso", "fim_subida": "aviso",
    "navegacao_encerrada": "fim",
}
_CURVAS = ("vire_", "levemente_", "acentuada_", "retorno", "mantenha_", "saida_", "rotatoria", "sair_rotatoria",
           "chegara_destino", "destino_")


def som_da_fala(pedacos):
    """O som que anuncia a fala (None = nenhum: ex. "siga em frente")."""
    for p in pedacos:
        if p in _DA_FALA:
            return _DA_FALA[p]
    if any(p.startswith(_CURVAS) for p in pedacos):
        return "curva"
    if any(p.startswith(("subida_", "descida_")) for p in pedacos):
        return "aviso"
    return None


class Sons:
    def __init__(self, volume="medio"):
        self.volume = VOLUMES.get(volume, 0.65)
        self._carregados = {}
        self.tocados = []           # (para os testes) os últimos nomes pedidos

    def carregar_todos(self, agendar):
        """Deixa os sons na memória ANTES de precisar (abrir o arquivo na hora de
        tocar dava um engasgo na tela). agendar(função, segundos): um som por
        vez, espalhados, para a abertura do app não sentir."""
        try:
            nomes = sorted(n[:-4] for n in os.listdir(PASTA) if n.endswith(".wav"))
        except OSError:
            return
        for k, nome in enumerate(nomes):
            agendar(lambda dt=0, n=nome: self._carregar(n), 1.5 + 0.12 * k)

    def _carregar(self, nome):
        try:
            if nome not in self._carregados:
                caminho = os.path.join(PASTA, nome + ".wav")
                self._carregados[nome] = SoundLoader.load(caminho) if os.path.exists(caminho) else None
        except Exception as e:
            print("[sons] carregar", nome, type(e).__name__)
            self._carregados[nome] = None
        return self._carregados.get(nome)

    def definir_volume(self, nome):
        self.volume = VOLUMES.get(nome, 0.65)

    def tocar(self, nome):
        """Toca o som (se existir e os sons estiverem ligados). Nunca levanta erro."""
        if not nome:
            return False
        self.tocados = (self.tocados + [nome])[-20:]
        if self.volume <= 0.0:
            return False
        try:
            som = self._carregar(nome)
            if som is None:
                return False
            if som.state == "play":
                som.stop()
            som.volume = self.volume
            som.play()
            return True
        except Exception as e:
            print("[sons]", nome, type(e).__name__, e)
            return False
