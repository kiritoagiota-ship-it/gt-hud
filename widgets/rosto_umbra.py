"""O rosto do Umbra na tela: grande no meio (quando chamado) ou pequeno no canto (nos avisos).

O desenho é o mesmo da página de prévia (widgets/umbra_pintor.py, feito pela placa de vídeo).
Ele é pintado numa textura fora da tela (Fbo) e a textura é posta no lugar: no modo grande a
textura tem só ESCALA_GRANDE do tamanho na tela (a fumaça e o brilho são macios, não perdem
nada, e a placa do celular trabalha bem menos).

O movimento (cabeça que vira, piscada, olhar, reações de cada estado) é o mesmo da prévia, por
tempo e não por quadro. A boca segue o VOLUME da fala que está tocando (voz.tocando): da
gravação, lido do próprio arquivo; da voz do celular, sílabas simuladas.

O shader devolve a cor já multiplicada pela transparência ("pré-multiplicada"); o Kivy mistura
de outro jeito, então a mistura é trocada só enquanto o rosto é desenhado (sem isso o brilho
encolhe e aparecem manchas cinza: medido em 13/10/2026).
"""
import array
import math
import random
import threading
import time
import wave

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Callback, ClearBuffers, ClearColor, Color, Fbo, Rectangle
from kivy.graphics import opengl as gl
from kivy.metrics import dp, sp
from kivy.properties import NumericProperty
from kivy.uix.widget import Widget

import tema
from widgets.comuns import Texto
from widgets.umbra_pintor import FONTE

ESCALA_GRANDE = 0.62        # resolução da textura no modo grande (o rosto fica grande na tela)
ESCALA_PEQUENO = 1.0
LADO_PEQUENO = dp(112)
ATRASO_SOM_S = 0.08         # o som sai um tiquinho depois do play: a boca espera
QUADROS_ENVELOPE = 50       # volume da fala: 50 medidas por segundo
VEU = 0.72                  # quanto o mapa escurece por trás dele grande

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

    def mola(self, nome, alvo, dt, freq, amort):
        m = self.molas.setdefault(nome, [alvo, 0.0])
        w = 2 * math.pi * freq
        m[1] += ((alvo - m[0]) * w * w - 2 * amort * w * m[1]) * dt
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
        u = {}
        u["giro"] = (self.mola("giroX", al["giroX"] + 0.22 * _deriva(t, 0) + 0.28 * ox
                               + (0.06 * math.sin(t * 2.7) if falando else 0.0), dt, 1.1, 0.55),
                     self.mola("giroY", al["giroY"] + 0.12 * _deriva(t, 4) + 0.30 * e, dt, 1.6, 0.45))
        u["olhar"] = (ox, oy)
        u["rolar"] = self.mola("rolar", al["rolar"] + 0.025 * _deriva(t, 8), dt, 1.2, 0.5)
        u["olho"] = _lim(self.mola("olho", al["olho"], dt, 3.0, 0.55), 0.05, 1.6)
        u["inclina"] = self.mola("inclina", al["inclina"] + 0.25 * e, dt, 2.2, 0.8)
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
_lendo = set()


def _ler_envelope(caminho):
    """Volume do WAV (16 bits) em QUADROS_ENVELOPE medidas por segundo, de 0 a 1."""
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
            trecho = amostras[i:i + passo:4]             # (uma em cada 4 basta para o volume)
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
    _lendo.discard(caminho)


def volume_da_fala(tocando, agora):
    """O volume da fala que está tocando (0 a 1), ou 0 se não há fala."""
    if not tocando:
        return 0.0
    caminho, t0, duracao = tocando
    el = agora - t0 - ATRASO_SOM_S
    if el < 0 or el > duracao:
        return 0.0
    if caminho:
        if caminho in _envelopes:
            env = _envelopes[caminho]
            if env:
                i = int(el * QUADROS_ENVELOPE)
                return env[i] if i < len(env) else 0.0
        elif caminho not in _lendo:
            _lendo.add(caminho)
            threading.Thread(target=_ler_envelope, args=(caminho,), daemon=True).start()
    # voz do celular (ou o arquivo ainda sendo lido): sílabas simuladas
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
        self.lugar_pequeno = None       # função (largura, altura) -> (x, y) do canto dele
        self.quebrado = False           # o desenho não compilou neste aparelho: não aparece
        self._fbo = None
        self._fbo_lado = 0
        self._ev = None
        self._t0 = time.monotonic()
        self._ultimo = None
        self._mistura = None
        with self.canvas:
            self._cor_veu = Color(0.004, 0.003, 0.016, 0.0)
            self._veu = Rectangle()
            Callback(self._mistura_pre)
            self._cor_rosto = Color(1, 1, 1, 0)
            self._ret = Rectangle()
            Callback(self._mistura_volta)
        self.lbl_ouvido = Texto(text="", font_size=sp(15), italic=True, color=tema.CIANO_FRACO,
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
            Animation(presenca=1.0, d=0.28, t="out_back").start(self)
        else:
            Animation(presenca=1.0, rx=x, ry=y, rlado=lado, d=0.30, t="out_quad").start(self)
        grande = modo == "grande"
        for lbl in (self.lbl_ouvido, self.lbl_fala):
            Animation.cancel_all(lbl)
            Animation(opacity=1.0 if grande else 0.0, d=0.25).start(lbl)
        if not grande:
            self.lbl_ouvido.text = self.lbl_fala.text = ""
        self._ligar()

    def esconder(self):
        Animation.cancel_all(self)
        a = Animation(presenca=0.0, d=0.22, t="in_quad")
        a.bind(on_complete=lambda *x: self._desligar())
        a.start(self)
        for lbl in (self.lbl_ouvido, self.lbl_fala):
            Animation.cancel_all(lbl)
            Animation(opacity=0.0, d=0.18).start(lbl)
        self.modo = None

    def definir_estado(self, nome):
        self.mov.mudar(nome, time.monotonic() - self._t0)

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
        return False

    # --- desenho -------------------------------------------------------------------
    def _alvo(self):
        W, H = self.width, self.height
        if self.modo == "grande":
            lado = min(W, H) * (0.80 if H >= W else 0.62)
            return (self.x + (W - lado) / 2.0, self.y + H * (0.60 if H >= W else 0.52) - lado / 2.0, lado)
        lado = LADO_PEQUENO
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
        base = self.ry - dp(8)
        self.lbl_fala.pos = (self.x + m, base - self.lbl_fala.height)
        self.lbl_ouvido.pos = (self.x + m, self.lbl_fala.y - self.lbl_ouvido.height)
        self._redesenhar()

    def _redesenhar(self, *a):
        p = self.presenca
        self._veu.pos, self._veu.size = self.pos, self.size
        self._cor_veu.a = VEU * p if self.modo == "grande" or (self.modo is None and self._veu_era) else 0.0
        escala = 0.86 + 0.14 * p
        lado = self.rlado * escala
        self._ret.pos = (self.rx + (self.rlado - lado) / 2.0, self.ry + (self.rlado - lado) / 2.0)
        self._ret.size = (lado, lado)
        self._cor_rosto.rgba = (p, p, p, p)            # (pré-multiplicada: a cor também some)
        if self._fbo is not None:
            self._ret.texture = self._fbo.texture

    @property
    def _veu_era(self):
        return self._cor_veu.a > 0.0

    def _mistura_pre(self, instr):
        if self._mistura is None:
            def um(v):
                try:
                    return int(v[0])
                except (TypeError, IndexError):
                    return int(v)
            self._mistura = tuple(um(gl.glGetIntegerv(p)) for p in (
                gl.GL_BLEND_SRC_RGB, gl.GL_BLEND_DST_RGB, gl.GL_BLEND_SRC_ALPHA, gl.GL_BLEND_DST_ALPHA))
        gl.glBlendFuncSeparate(gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA, gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA)

    def _mistura_volta(self, instr):
        if self._mistura is not None:
            gl.glBlendFuncSeparate(*self._mistura)

    def _preparar_fbo(self):
        escala = ESCALA_GRANDE if self.modo == "grande" else ESCALA_PEQUENO
        _, _, lado_tela = self._alvo()
        lado = max(64, int(lado_tela * escala))
        if self._fbo is not None and abs(lado - self._fbo_lado) < 8:
            return True
        fbo = Fbo(size=(lado, lado), with_stencilbuffer=False)
        fbo.shader.fs = FONTE
        if not fbo.shader.success:
            print("[umbra] o desenho do rosto não compilou neste aparelho")
            self.quebrado = True
            return False
        with fbo:
            ClearColor(0, 0, 0, 0)
            ClearBuffers()
            Callback(self._mistura_pre)
            Color(1, 1, 1, 1)
            Rectangle(pos=(0, 0), size=(lado, lado))
            Callback(self._mistura_volta)
        # o Fbo só é pintado se fizer parte do desenho do widget (antes do rosto, que usa a textura dele)
        if self._fbo is not None:
            self.canvas.before.remove(self._fbo)
        self.canvas.before.add(fbo)
        self._fbo, self._fbo_lado = fbo, lado
        self._ret.texture = fbo.texture
        return True

    def _ligar(self):
        if not self._preparar_fbo():
            self.presenca = 0.0
            return
        if self._ev is None:
            self._ultimo = None
            self._ev = Clock.schedule_interval(self._quadro, 0)

    def _desligar(self):
        if self.presenca > 0.01:
            return
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None
        self._cor_veu.a = 0.0

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
        f = self._fbo
        if f is None:
            return
        f["u_res"] = [float(self._fbo_lado), float(self._fbo_lado)]
        f["u_t"] = float(t)
        for k in ("boca", "olho", "inclina", "feliz", "torto", "alerta", "escuta", "rolar", "palpebra",
                  "enfase", "brilho", "lingua"):
            f["u_" + k] = float(u[k])
        f["u_giro"] = [float(u["giro"][0]), float(u["giro"][1])]
        f["u_olhar"] = [float(u["olhar"][0]), float(u["olhar"][1])]
        f.ask_update()
        self.canvas.ask_update()
