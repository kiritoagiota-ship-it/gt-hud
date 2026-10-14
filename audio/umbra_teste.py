"""Teste do Umbra (Ajustes > Sistema > Testar o Umbra): liga as peças dele UMA DE CADA VEZ.

Pedido do dono (14/10/2026): no Galaxy S23 Ultra (Adreno 740, Android 16) o app fecha ao chamar o
Umbra, sem erro do Python (a queda é fora dele), e as versões 1.0.84 a 1.0.87 não acharam a causa
tirando suspeitos às cegas. Aqui cada peça é marcada no disco antes de começar (diagnostico.etapa):
se o app cair, a próxima abertura diz em qual peça foi (main.py mostra no mapa e anota no registro).

As peças vão da mais simples para a mais complexa: a fala, o rosto em imagem com legenda, um
desenho mínimo na placa de vídeo, o desenho só da cabeça, cabeça e olhos, cabeça, olhos e boca,
o desenho leve, o completo e o microfone.
"""
from kivy.clock import Clock

import diagnostico
import tema

ETAPA = "teste_umbra:"
# um desenho mínimo: só um degradê (testa o caminho do desenho ao vivo, sem o desenho do Umbra)
MINIMO = """#ifdef GL_ES
precision mediump float;
#endif
varying vec2 tex_coord0;
uniform float u_presenca;
void main() { gl_FragColor = vec4(tex_coord0.x, 0.25, tex_coord0.y, 0.85 * u_presenca); }
"""
LEVE = "#define LEVE\n"
PASSOS = [
    # nome, o que aparece na tela, segundos
    ("fala", "só a fala gravada", 3.5),
    ("imagem", "o rosto em imagem, com legenda e fundo escuro", 3.0),
    ("desenho_minimo", "um desenho mínimo na placa de vídeo", 3.0),
    ("so_cabeca", "o desenho só da cabeça", 3.0),
    ("cabeca_olhos", "o desenho da cabeça e dos olhos", 3.0),
    ("cabeca_olhos_boca", "cabeça, olhos e boca (leve)", 3.0),
    ("leve", "o desenho leve inteiro", 3.0),
    ("completo", "o desenho completo", 3.0),
    ("microfone", "o microfone", 3.5),
]
DEFINICOES = {
    "so_cabeca": LEVE + "#define SEM_BOCA\n#define SEM_OLHOS\n#define SEM_EXTRAS\n",
    "cabeca_olhos": LEVE + "#define SEM_BOCA\n#define SEM_EXTRAS\n",
    "cabeca_olhos_boca": LEVE + "#define SEM_EXTRAS\n",
    "leve": LEVE,
    "completo": "",
}


def descricao(etapa):
    """'teste_umbra:so_cabeca' -> 'o desenho só da cabeça' (para o aviso depois de uma queda)."""
    nome = etapa[len(ETAPA):] if etapa.startswith(ETAPA) else etapa
    return next((d for n, d, s in PASSOS if n == nome), nome)


class TesteUmbra:
    def __init__(self, app):
        self.app = app
        self.i = -1
        self._ev = None
        self.ativo = False

    def rosto(self):
        return self.app.sm.get_screen("mapa").rosto_umbra

    def avisar(self, texto, segundos=4.0):
        print("[teste umbra]", texto, flush=True)
        try:
            self.app.sm.get_screen("mapa").mensagem(texto, tema.CIANO, segundos)
        except Exception:
            pass

    def comecar(self):
        if self.ativo:
            return
        self.ativo = True
        self.app.umbra.fechar()
        self.app.umbra.pausado = True          # a escuta do nome não atrapalha o teste
        r = self.rosto()
        r.em_teste = True
        self.i = -1
        self.avisar("Teste do Umbra: começando (%d peças, uma de cada vez)" % len(PASSOS), 3.0)
        self._ev = Clock.schedule_once(self._proximo, 1.5)

    def _encerrar_passo(self):
        if self.i < 0:
            return
        nome = PASSOS[self.i][0]
        r = self.rosto()
        r.esconder()
        if nome == "microfone":
            self.app.escuta.parar()
        diagnostico.etapa_ok(ETAPA + nome)
        print("[teste umbra] passou: %s" % nome, flush=True)

    def _proximo(self, dt=None):
        self._encerrar_passo()
        self.i += 1
        if self.i >= len(PASSOS):
            self._terminar()
            return
        nome, texto, segundos = PASSOS[self.i]
        self.avisar("Teste %d/%d: %s" % (self.i + 1, len(PASSOS), texto), segundos + 0.4)
        diagnostico.etapa(ETAPA + nome)
        try:
            self._executar(nome, texto)
        except Exception as e:                  # erro do Python: anota e segue para a próxima peça
            print("[teste umbra] %s deu erro: %s %s" % (nome, type(e).__name__, e), flush=True)
        self._ev = Clock.schedule_once(self._proximo, segundos)

    def _executar(self, nome, texto):
        app, r = self.app, self.rosto()
        if nome == "fala":
            app.voz.falar(["umbra_oi_1"], 3)
            return
        if nome == "microfone":
            if not app.umbra.microfone:
                print("[teste umbra] microfone sem permissão: peça pulada", flush=True)
                return
            app.escuta.ouvir(1.0, conversa=False)
            return
        if nome == "imagem":
            r.simples = True
        else:
            r.simples = False
            r.fonte_propria = MINIMO if nome == "desenho_minimo" else None
            r.definicoes = DEFINICOES.get(nome, "")
            r.recompilar()
        r.mostrar("grande")
        r.legenda("teste", "Teste %d/%d: %s" % (self.i + 1, len(PASSOS), texto))

    def _terminar(self):
        self.ativo = False
        r = self.rosto()
        r.em_teste = False
        r.fonte_propria = None
        r.definicoes = ""
        r.simples = r.nivel >= 2
        r.recompilar()
        self.app.umbra.pausado = False
        self.avisar("Teste do Umbra: todas as peças passaram sem fechar o app", 8.0)
