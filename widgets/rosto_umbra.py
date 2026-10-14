"""O rosto do Umbra na tela: grande no meio (quando chamado) ou pequeno no canto (nos avisos).

O desenho é o mesmo da página de prévia (widgets/umbra_pintor.py, feito pela placa de vídeo),
pintado DIRETO na tela, do jeito padrão do Kivy: um RenderContext com o desenho e um retângulo
(a posição de cada ponto vem da coordenada da textura do retângulo, #define NO_APP).

Até a 1.0.86 ele era pintado numa textura escondida (Fbo), com a mistura do OpenGL trocada por
código Python no meio do desenho, e o volume da fala era lido numa thread: no Galaxy S23 Ultra
(Adreno 740, Android 16) o app caía na hora de pintar, até com o desenho leve. Agora não há Fbo,
nem troca de mistura (o próprio desenho entrega a cor no formato que o Kivy mistura), nem thread.

Até a 1.0.88 o RenderContext nascia com o desenho padrão do Kivy e depois recebia o do Umbra
(shader.fs = ...: o Kivy refaz o programa já usado na placa de vídeo e reaproveita os endereços
anotados antes da troca). No mesmo celular, até um degradê de uma linha caía assim (Teste do
Umbra, 14/10/2026). Agora cada desenho ganha um RenderContext NOVO, que já nasce com ele.

Se mesmo assim o desenho derrubar o app (diagnostico.etapa), a escada desce um degrau por
versão: 0 desenho completo, 1 leve (#define LEVE), 2 imagens prontas (dados/umbra).

O movimento (cabeça que vira, piscada, olhar, reações de cada estado) é o mesmo da prévia, por
tempo e não por quadro. A boca segue o VOLUME da fala que está tocando (voz.tocando): da
gravação, lido do próprio arquivo; da voz do celular, sílabas simuladas.
"""
import array
import math
import os
import random
import time
import wave

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, InstructionGroup, Rectangle, RenderContext
from kivy.graphics import opengl as gl
from kivy.metrics import dp, sp
from kivy.properties import NumericProperty
from kivy.uix.widget import Widget

import diagnostico
import tema
from widgets.comuns import Texto
from widgets.umbra_pintor import FONTE

LADO_PEQUENO = dp(112)
LADO_MEDIO = dp(190)         # chamado com a moto andando: no canto, sem escurecer o mapa
# aparecer/sumir (pedido do dono, 14/10/2026: "sobe das sombras"): a poça abre, ele sobe dela
# escuro, dá um leve impulso, os olhos acendem por último e a poça fecha; sumindo, os olhos
# apagam primeiro e ele afunda. O movimento está no desenho (u_presenca); aqui só o tempo.
ENTRA_S, SAI_S = 0.95, 0.70
OLHOS_DE = 0.72             # presença a partir da qual os olhos acendem (entrando) / até onde apagam (saindo)
ATRASO_SOM_S = 0.08         # o som sai um tiquinho depois do play: a boca espera
QUADROS_ENVELOPE = 50       # volume da fala: 50 medidas por segundo
VEU = 0.72                  # quanto o mapa escurece por trás dele grande
ETAPA_ROSTO = "umbra_rosto"  # (diagnostico.etapa) desenhar o rosto ao vivo
PASTA_IMAGENS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados", "umbra")

FALA_ATE = {"falando": 99.0}
ALVOS = {
    # olho, inclina, feliz, torto, alerta, escuta, boca (sem voz), giroX, giroY, rolar, pálpebra
    "parado":    dict(olho=1.0, inclina=0.0, feliz=0.0, torto=0.0, alerta=0.0, escuta=0.0, boca=0.0,
                      giroX=0.0, giroY=0.0, rolar=0.0, palpebra=0.08),
    "ouvindo":   dict(olho=1.32, inclina=-0.15, feliz=0.0, torto=0.0, alerta=0.0, escuta=1.0, boca=0.14,
                      giroX=0.0, giroY=0.18, rolar=0.0, palpebra=0.0),
    "falando":   dict(olho=1.0, inclina=0.0, feliz=0.0, torto=0.0, alerta=0.0, escuta=0.0, boca=0.0,
                      giroX=0.0, giroY=0.0, rolar=0.0, palpebra=0.05),
    "confirmou": dict(olho=1.0, inclina=-0.35, feliz=1.0, torto=0.0, alerta=0.0, escuta=0.0, boca=0.08,
                      giroX=0.0, giroY=0.05, rolar=0.0, palpebra=0.0),
    "confuso":   dict(olho=1.0, inclina=-0.2, feliz=0.0, torto=1.0, alerta=0.0, escuta=0.0, boca=0.16,
                      giroX=0.25, giroY=-0.05, rolar=0.12, palpebra=0.05),
    "alerta":    dict(olho=0.8, inclina=0.9, feliz=0.0, torto=0.0, alerta=1.0, escuta=0.0, boca=0.05,
                      giroX=0.0, giroY=-0.10, rolar=0.0, palpebra=0.0),
    # procurando o lugar: olhos estreitos, cabeça baixa varrendo de um lado a outro, fungadas
    "farejando": dict(olho=0.62, inclina=0.35, feliz=0.0, torto=0.0, alerta=0.0, escuta=0.0, boca=0.06,
                      giroX=0.0, giroY=-0.12, rolar=0.0, palpebra=0.30),
}


def _lim(v, a, b):
    return max(a, min(b, v))


def _deriva(t, s):
    """Um vaivém lento que nunca se repete igual."""
    return math.sin(t * 0.37 + s) * 0.6 + math.sin(t * 0.91 + s * 2.1) * 0.3 + math.sin(t * 1.73 + s * 3.7) * 0.1


class Movimento:
    """Cada número do rosto anda como uma mola (vai até o alvo, passa um pouco e assenta)."""

    def __init__(self, sorteio=None):
        self.r = sorteio or random.Random()
        self.molas = {}
        self.estado = "parado"
        self.prox_piscada, self.piscada_ini, self.dupla = 1.6, -10.0, False
        self.olhar_alvo, self.prox_olhar = [0.0, 0.0], 1.2
        self.direcao = 0.0              # -1 esquerda, 1 direita: olha para o lado da próxima curva

    def mola(self, nome, alvo, dt, freq, amort):
        # conta "implícita": estável a qualquer velocidade de tela. A conta direta de antes divergia
        # a 30 quadros/s (o olhar ia a 1e38 e o desenho estourava em branco; achado em 14/10/2026)
        m = self.molas.setdefault(nome, [alvo, 0.0])
        w = 2 * math.pi * freq
        m[1] = (m[1] + (alvo - m[0]) * w * w * dt) / (1.0 + 2 * amort * w * dt + w * w * dt * dt)
        m[0] += m[1] * dt
        return m[0]

    def empurrar(self, nome, v):
        if nome in self.molas:
            self.molas[nome][1] += v

    def mudar(self, nome, agora):
        if nome not in ALVOS or nome == self.estado:
            return
        self.estado = nome
        if nome == "alerta":                       # susto
            self.empurrar("olho", 9); self.empurrar("brilho", 16); self.empurrar("giroY", -5); self.empurrar("giroX", 1.5)
        elif nome == "confirmou":                  # aceno
            self.empurrar("giroY", 7); self.empurrar("brilho", 4)
        elif nome == "confuso":                    # cabeça de lado
            self.empurrar("rolar", 1.4); self.empurrar("giroX", 2.5)
        elif nome == "farejando":                  # baixa a cabeça para farejar
            self.empurrar("giroY", -3); self.empurrar("olho", -3)
        elif nome == "ouvindo":                    # se inclina para ouvir, olha para você
            self.empurrar("giroY", 2.5); self.empurrar("olho", 4)
            self.prox_olhar = agora

    @staticmethod
    def _curva(f):
        if f < 0 or f > 0.27:
            return 0.0
        if f < 0.07:
            return (f / 0.07) ** 2
        if f < 0.10:
            return 1.0
        b = (f - 0.10) / 0.17
        return 1 - b * b * (3 - 2 * b)

    def _piscada(self, t):
        if t > self.prox_piscada:
            self.piscada_ini, self.dupla = t, self.r.random() < 0.15
            self.prox_piscada = t + 2.4 + self.r.random() * 3.6 + (0.35 if self.dupla else 0)
        f = t - self.piscada_ini
        return max(self._curva(f), self._curva(f - 0.30) if self.dupla else 0.0)

    def _olhar(self, t):
        if self.estado == "farejando":           # varre de um lado a outro, junto com a cabeça
            return [0.75 * math.sin(t * 1.9), 0.12]
        if self.direcao:                          # aviso de rota: olha para o lado da curva
            return [0.8 * self.direcao, 0.05 + 0.08 * math.sin(t * 0.9)]
        if t > self.prox_olhar:
            atento = self.estado in ("ouvindo", "falando")
            longe = self.r.random() < 0.3
            self.olhar_alvo = ([(self.r.random() - 0.5) * 0.35, (self.r.random() - 0.5) * 0.25] if atento
                               else [(self.r.random() - 0.5) * (1.8 if longe else 0.8), (self.r.random() - 0.5) * 0.7])
            self.prox_olhar = t + 0.7 + self.r.random() * 2.6
        return self.olhar_alvo

    def quadro(self, t, dt, voz_v, nivel_ouvindo=0.0):
        """Os números do desenho neste instante. voz_v: volume da fala agora (0 a 1)."""
        al = ALVOS[self.estado]
        e = _lim((voz_v - 0.62) / 0.30, 0.0, 1.0)          # sílaba forte: ênfase
        oa = self._olhar(t)
        ox = self.mola("olharX", oa[0], dt, 5.5, 1.0)
        oy = self.mola("olharY", oa[1], dt, 5.5, 1.0)
        falando = voz_v > 0.02
        farejando = self.estado == "farejando"
        fungada = max(0.0, math.sin(t * 9.0)) ** 6 * (1.0 if math.sin(t * 1.3) > 0.2 else 0.0) if farejando else 0.0
        u = {}
        u["giro"] = (self.mola("giroX", al["giroX"] + 0.22 * _deriva(t, 0) + 0.28 * ox
                               + (0.30 * math.sin(t * 1.9) if farejando else 0.0) + 0.30 * self.direcao
                               + (0.06 * math.sin(t * 2.7) if falando else 0.0), dt, 1.1, 0.55),
                     self.mola("giroY", al["giroY"] + 0.12 * _deriva(t, 4) + 0.30 * e, dt, 1.6, 0.45))
        u["olhar"] = (ox, oy)
        u["rolar"] = self.mola("rolar", al["rolar"] + 0.025 * _deriva(t, 8), dt, 1.2, 0.5)
        u["olho"] = _lim(self.mola("olho", al["olho"], dt, 3.0, 0.55), 0.05, 1.6)
        u["inclina"] = self.mola("inclina", al["inclina"] + 0.25 * e + 0.25 * fungada, dt, 2.2, 0.8)
        for k in ("feliz", "torto"):
            u[k] = _lim(self.mola(k, al[k], dt, 2.2, 0.9), 0.0, 1.0)
        u["alerta"] = _lim(self.mola("alerta", al["alerta"], dt, 2.5, 1.0), 0.0, 1.0)
        u["escuta"] = _lim(self.mola("escuta", al["escuta"], dt, 2.0, 1.0), 0.0, 1.0)
        u["brilho"] = _lim(self.mola("brilho", 1 + 0.05 * math.sin(t * 1.1) + 0.35 * nivel_ouvindo, dt, 2.0, 0.5),
                           0.5, 2.2)
        u["boca"] = _lim(self.mola("boca", 0.10 + voz_v * 0.75 if falando else al["boca"], dt, 7.0, 0.85), 0.0, 1.0)
        u["enfase"] = _lim(self.mola("enfase", e, dt, 6.0, 0.9), 0.0, 1.0)
        u["palpebra"] = _lim(max(self._piscada(t), al["palpebra"]), 0.0, 1.0)
        u["lingua"] = 0.0             # a língua fica de lado por enquanto (pedido do dono, 14/10/2026)
        return u



# ---------------------------------------------------------------- o volume da fala gravada
_envelopes = {}


def _ler_envelope(caminho):
    """Volume do WAV (16 bits) em QUADROS_ENVELOPE medidas por segundo, de 0 a 1. Lido uma vez por
    frase (as frases se repetem: fica guardado), na hora, sem thread."""
    try:
        with wave.open(caminho, "rb") as w:
            taxa, canais, largura = w.getframerate(), w.getnchannels(), w.getsampwidth()
            dados = w.readframes(w.getnframes())
        if largura != 2:
            raise ValueError("WAV de %d bytes por amostra" % largura)
        amostras = array.array("h")
        amostras.frombytes(dados)
        passo = max(1, int(taxa * canais / QUADROS_ENVELOPE))
        valores = []
        for i in range(0, len(amostras), passo):
            trecho = amostras[i:i + passo:8]             # (uma em cada 8 basta para o volume)
            if trecho:
                valores.append(math.sqrt(sum(x * x for x in trecho) / len(trecho)))
        topo = max(valores) if valores else 0.0
        env = [min(1.0, (v / topo) ** 0.7 * 1.08) if topo > 0 else 0.0 for v in valores]
    except Exception as e:
        print("[umbra] volume da fala:", e)
        env = None
    if len(_envelopes) > 40:
        _envelopes.clear()
    _envelopes[caminho] = env
    return env


def volume_da_fala(tocando, agora):
    """O volume da fala que está tocando (0 a 1), ou 0 se não há fala."""
    if not tocando:
        return 0.0
    caminho, t0, duracao = tocando
    el = agora - t0 - ATRASO_SOM_S
    if el < 0 or el > duracao:
        return 0.0
    if caminho:
        env = _envelopes[caminho] if caminho in _envelopes else _ler_envelope(caminho)
        if env:
            i = int(el * QUADROS_ENVELOPE)
            return env[i] if i < len(env) else 0.0
    # voz do celular (ou arquivo que não deu para ler): sílabas simuladas
    silaba = abs(math.sin(el * 9.0))
    frase = 0.55 + 0.45 * math.sin(el * 2.3 + 1.0)
    return _lim(silaba * frase, 0.0, 1.0)


# ---------------------------------------------------------------- o widget
class RostoUmbra(Widget):
    presenca = NumericProperty(0.0)     # 0 escondido, 1 inteiro na tela
    rx = NumericProperty(0.0)           # onde o rosto está (anima entre o grande e o pequeno)
    ry = NumericProperty(0.0)
    rlado = NumericProperty(0.0)

    def __init__(self, voz=None, escuta=None, **kw):
        super().__init__(**kw)
        self.voz = voz
        self.escuta = escuta
        self.modo = None
        self.mov = Movimento()
        self.ao_tocar_fora = None       # tocou na tela com ele grande: fecha
        self.lugar_pequeno = None       # função (largura, altura, lado) -> (x, y) do canto dele
        self.quebrado = False           # o desenho não compilou neste aparelho: não aparece
        self.simples = False            # usa as imagens prontas (o desenho ao vivo derrubou o app aqui)
        self.nivel = 0                  # 0 desenho completo, 1 leve (sem língua, saliva, fileira de trás...)
        self._texturas = {}
        self._bob = 0.0
        self._quadros_ok = -1
        self._avisou_placa = False
        self._compilado = False
        # Teste do Umbra (umbra_teste.py): desenho próprio ou partes desligadas, sem a etapa de sempre
        self.em_teste = False
        self.fonte_propria = None
        self.definicoes = ""
        self._ev = None
        self._t0 = time.monotonic()
        self._ultimo = None
        self._entrando = False
        with self.canvas:
            self._cor_veu = Color(0.004, 0.003, 0.016, 0.0)
            self._veu = Rectangle()
            # o desenho ao vivo: um RenderContext só para ele, criado já com o desenho (_compilar)
            self._lugar_vivo = InstructionGroup()
            # o modo simples: uma imagem pronta comum
            self._cor_img = Color(1, 1, 1, 0)
            self._ret_img = Rectangle(size=(0, 0))
        self._rc = None
        self._ret_vivo = None
        self.lbl_ouvido = Texto(text="", font_size=sp(15), color=tema.CIANO_FRACO,
                                halign="center", size_hint=(None, None), opacity=0)
        self.lbl_fala = Texto(text="", font_size=sp(19), bold=True, color=tema.BRANCO,
                              halign="center", size_hint=(None, None), opacity=0)
        self.add_widget(self.lbl_ouvido)
        self.add_widget(self.lbl_fala)
        self.bind(size=self._geometria, pos=self._geometria, presenca=self._redesenhar,
                  rx=self._redesenhar, ry=self._redesenhar, rlado=self._redesenhar)

    # --- o que o cérebro (umbra.py) chama ---------------------------------------------
    def mostrar(self, modo):
        if self.quebrado:
            return
        primeira = self.presenca < 0.05
        self.modo = modo
        x, y, lado = self._alvo()
        Animation.cancel_all(self)
        if primeira:
            self.rx, self.ry, self.rlado = x, y, lado
            self._entrando = True
            Animation(presenca=1.0, d=ENTRA_S if not self.simples else 0.28,
                      t="linear" if not self.simples else "out_quad").start(self)
        else:
            Animation(presenca=1.0, rx=x, ry=y, rlado=lado, d=0.30, t="out_quad").start(self)
        conversa = modo in ("grande", "medio")
        for lbl in (self.lbl_ouvido, self.lbl_fala):
            Animation.cancel_all(lbl)
            Animation(opacity=1.0 if conversa else 0.0, d=0.25).start(lbl)
        if not conversa:
            self.lbl_ouvido.text = self.lbl_fala.text = ""
        self._ligar()

    def esconder(self):
        Animation.cancel_all(self)
        self.mov.direcao = 0.0
        self._entrando = False
        a = Animation(presenca=0.0, d=SAI_S if not self.simples else 0.22,
                      t="linear" if not self.simples else "in_quad")
        a.bind(on_complete=lambda *x: self._desligar())
        a.start(self)
        for lbl in (self.lbl_ouvido, self.lbl_fala):
            Animation.cancel_all(lbl)
            Animation(opacity=0.0, d=0.18).start(lbl)
        self.modo = None

    def definir_estado(self, nome):
        self.mov.mudar(nome, time.monotonic() - self._t0)

    def olhar_para(self, lado):
        """-1 esquerda, 1 direita, 0 livre (nos avisos de rota: o lado da próxima curva)."""
        self.mov.direcao = float(lado)

    def legenda(self, ouvido=None, fala=None):
        """O que a pessoa disse (entre aspas) e o que ele diz. None = deixa como está."""
        if ouvido is not None:
            self.lbl_ouvido.text = ("“%s”" % ouvido) if ouvido else ""
        if fala is not None:
            self.lbl_fala.text = fala
        self._geometria()

    # --- toque ---------------------------------------------------------------------
    def on_touch_down(self, toque):
        if self.modo == "grande" and self.presenca > 0.3:
            if self.ao_tocar_fora is not None:
                self.ao_tocar_fora()
            return True                  # com ele grande, o mapa por baixo não recebe o toque
        if (self.modo == "medio" and self.presenca > 0.3 and self.rx <= toque.x <= self.rx + self.rlado
                and self.ry <= toque.y <= self.ry + self.rlado):
            if self.ao_tocar_fora is not None:
                self.ao_tocar_fora()
            return True                  # médio: só o toque NELE fecha; o mapa segue funcionando
        return False

    # --- desenho -------------------------------------------------------------------
    def _alvo(self):
        W, H = self.width, self.height
        if self.modo == "grande":
            lado = min(W, H) * (0.80 if H >= W else 0.62)
            return (self.x + (W - lado) / 2.0, self.y + H * (0.60 if H >= W else 0.52) - lado / 2.0, lado)
        lado = LADO_MEDIO if self.modo == "medio" else LADO_PEQUENO
        if self.lugar_pequeno is not None:
            x, y = self.lugar_pequeno(W, H, lado)
            return (self.x + x, self.y + y, lado)
        return (self.x + W - lado - dp(10), self.y + H - lado - dp(150), lado)

    def _geometria(self, *a):
        if self.modo is not None:
            x, y, lado = self._alvo()
            if self.presenca >= 0.999:
                self.rx, self.ry, self.rlado = x, y, lado
        m = dp(16)
        larg = self.width - 2 * m
        for lbl, alt in ((self.lbl_ouvido, dp(44)), (self.lbl_fala, dp(64))):
            lbl.size = (larg, alt)
            lbl.text_size = (larg, None)
        self._redesenhar()

    def _redesenhar(self, *a):
        p = self.presenca
        # a legenda acompanha o rosto (inclusive quando ele muda de tamanho sem sumir)
        base = self.ry - dp(8)
        self.lbl_fala.pos = (self.x + dp(16), base - self.lbl_fala.height)
        self.lbl_ouvido.pos = (self.x + dp(16), self.lbl_fala.y - self.lbl_ouvido.height)
        self._veu.pos, self._veu.size = self.pos, self.size
        self._cor_veu.a = VEU * p if self.modo == "grande" or (self.modo is None and self._cor_veu.a > 0.0) else 0.0
        escala = (0.86 + 0.14 * p) if self.simples else 1.0   # ao vivo, quem anima é a subida
        lado = self.rlado * escala
        pos = (self.rx + (self.rlado - lado) / 2.0, self.ry + (self.rlado - lado) / 2.0)
        visivel = p > 0.001
        if self.simples:
            self._ret_img.pos = (pos[0], pos[1] + self._bob)
            self._ret_img.size = (lado, lado) if visivel else (0, 0)
            self._cor_img.a = p
            if self._ret_vivo is not None:
                self._ret_vivo.size = (0, 0)
        elif self._ret_vivo is not None:
            self._ret_vivo.pos = pos
            self._ret_vivo.size = (lado, lado) if (visivel and self._compilado) else (0, 0)
            self._ret_img.size = (0, 0)

    # --- o modo simples: imagens prontas (dados/umbra), sem desenho ao vivo ---------------------
    def _textura(self, nome):
        if nome not in self._texturas:
            try:
                from kivy.core.image import Image as ImagemKivy
                self._texturas[nome] = ImagemKivy(os.path.join(PASTA_IMAGENS, nome + ".png")).texture
            except Exception as e:
                print("[umbra] imagem %s: %s" % (nome, e))
                self._texturas[nome] = None
        return self._texturas[nome]

    def _compilar(self):
        """O desenho ao vivo, compilado uma vez (completo ou leve, conforme o degrau)."""
        if self._compilado:
            return True
        fonte = self.fonte_propria or ("#define NO_APP\n" + self.definicoes
                                       + ("#define LEVE\n" if self.nivel == 1 else "") + FONTE)
        # um RenderContext NOVO, que já nasce com o desenho (sem refazer um programa já usado)
        try:
            rc = RenderContext(fs=fonte, use_parent_projection=True, use_parent_modelview=True,
                               use_parent_frag_modelview=True)
            ok = rc.shader.success
        except Exception as e:
            print("[umbra] o desenho do rosto não ligou: %s" % e)
            ok = False
        if not ok:
            print("[umbra] o desenho do rosto não compilou neste aparelho")
            self.quebrado = True
            return False
        with rc:
            Color(1, 1, 1, 1)
            ret = Rectangle(size=(0, 0))
        self._lugar_vivo.clear()
        self._lugar_vivo.add(rc)
        self._rc, self._ret_vivo = rc, ret
        self._compilado = True
        return True

    def aquecer(self):
        """Monta e desenha o rosto uma vez, invisível, logo depois que o app abre: senão a 1ª
        chamada trava (~0,5 s no PC, mais no celular) montando o desenho antes de ele subir."""
        if self.simples or self.quebrado or self._compilado or self.modo is not None:
            return
        diagnostico.etapa(ETAPA_ROSTO)          # (se derrubar o app, a escada de sempre vale)
        if not self._compilar():
            diagnostico.etapa_ok(ETAPA_ROSTO)
            return
        self._quadro(0)                         # u_presenca 0: nada aparece
        self._ret_vivo.pos, self._ret_vivo.size = (self.x, self.y), (dp(4), dp(4))
        Clock.schedule_once(self._fim_aquecer, 0.6)

    def _fim_aquecer(self, dt):
        if self.modo is None and self._ret_vivo is not None:
            self._ret_vivo.size = (0, 0)
        diagnostico.etapa_ok(ETAPA_ROSTO)
        print("[umbra] rosto pronto (desenho montado com antecedência)", flush=True)

    def recompilar(self):
        """O próximo mostrar() compila o desenho de novo (o teste troca as partes)."""
        self._compilado = False
        self.quebrado = False

    def _ligar(self):
        if self.simples:
            self._ret_img.texture = self._textura("parado")
        else:
            # etapa arriscada: se o app cair aqui (placa de vídeo), na próxima vez ele desce um degrau
            if not self.em_teste:
                diagnostico.etapa(ETAPA_ROSTO)
            print("[umbra] rosto: preparando o desenho %s, direto na tela" % ("leve" if self.nivel == 1 else "completo"),
                  flush=True)
            if not self._avisou_placa:
                self._avisou_placa = True
                try:
                    def texto(v):
                        return v.decode("ascii", "replace") if isinstance(v, bytes) else str(v)
                    print("[umbra] placa de vídeo: %s | %s" % (texto(gl.glGetString(gl.GL_RENDERER)),
                                                           texto(gl.glGetString(gl.GL_VERSION))), flush=True)
                except Exception:
                    pass
            if not self._compilar():
                if not self.em_teste:
                    diagnostico.etapa_ok(ETAPA_ROSTO)
                self.presenca = 0.0
                return
            print("[umbra] rosto: desenho compilado", flush=True)
            self._quadros_ok = 0 if not self.em_teste else -1
        if self._ev is None:
            self._ultimo = None
            self._quadro(0)                   # os números já certos antes do primeiro quadro na tela
            self._ev = Clock.schedule_interval(self._quadro, 0)
        self._redesenhar()

    def _desligar(self):
        if self.presenca > 0.01:
            return
        if self._quadros_ok >= 0:            # sumiu antes de 0,75 s, mas sem cair: a etapa passou
            self._quadros_ok = -1
            diagnostico.etapa_ok(ETAPA_ROSTO)
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None
        self._cor_veu.a = 0.0
        self._redesenhar()

    def _quadro(self, dt):
        agora = time.monotonic()
        t = agora - self._t0
        dt = _lim(dt if self._ultimo is not None else 1 / 60.0, 0.001, 1 / 30.0)
        self._ultimo = agora
        v = volume_da_fala(getattr(self.voz, "tocando", None), agora) if self.voz is not None else 0.0
        nivel = self.escuta.nivel() if (self.escuta is not None and self.mov.estado == "ouvindo") else 0.0
        if v > 0.02 and self.mov.estado in ("parado", "ouvindo"):
            self.mov.mudar("falando", t)
        u = self.mov.quadro(t, dt, v, nivel)
        if self.simples:
            estado = self.mov.estado
            nome = estado if estado in ("alerta", "confirmou", "confuso", "ouvindo") else (
                "falando" if v > 0.30 else "parado")
            if estado == "ouvindo" and v > 0.30:
                nome = "falando"
            tex = self._textura(nome)
            if tex is not None:
                self._ret_img.texture = tex
            self._bob = math.sin(t * 1.3) * dp(3) + u["boca"] * dp(2)
            self._redesenhar()
            return
        if not self._compilado or self._rc is None:
            return
        if self._quadros_ok >= 0:
            self._quadros_ok += 1
            if self._quadros_ok >= 45:          # uns 0,75 s desenhando sem cair: a etapa passou
                self._quadros_ok = -1
                diagnostico.etapa_ok(ETAPA_ROSTO)
                print("[umbra] rosto: desenhando sem problema", flush=True)
        rc = self._rc
        lado = max(1.0, float(self._ret_vivo.size[0]))
        rc["u_res"] = [lado, lado]
        rc["u_t"] = float(t)
        rc["u_presenca"] = float(self.presenca)
        # os olhos: acendem no fim da subida (com um lampejo) e apagam antes de ele afundar
        f = _lim((self.presenca - OLHOS_DE) / (1.0 - OLHOS_DE), 0.0, 1.0)
        f = f * f * (3 - 2 * f)
        lampejo = 0.9 * math.sin(math.pi * f) if self._entrando and self.presenca < 0.999 else 0.0
        for k in ("boca", "olho", "inclina", "feliz", "torto", "alerta", "escuta", "rolar", "enfase", "lingua"):
            rc["u_" + k] = float(u[k])
        rc["u_brilho"] = float(u["brilho"] * (0.04 + 0.96 * f) + lampejo)
        rc["u_palpebra"] = float(max(u["palpebra"], 1.0 - f))   # sobe de olhos fechados; abrem no alto
        rc["u_giro"] = [float(u["giro"][0]), float(u["giro"][1])]
        rc["u_olhar"] = [float(u["olhar"][0]), float(u["olhar"][1])]
        rc.ask_update()
