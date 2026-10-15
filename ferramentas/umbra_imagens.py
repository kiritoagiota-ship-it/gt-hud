"""Imagens prontas do rosto do Umbra (dados/umbra/<estado>.png), para o MODO SIMPLES.

O rosto normal é desenhado ao vivo pela placa de vídeo (widgets/umbra_pintor.py). Se num
celular esse desenho derrubar o app, o app passa a mostrar estas imagens (widgets/rosto_umbra.py),
trocando de uma para outra conforme o estado e a fala.

Rodar da raiz do projeto, no PC (abre uma janela no 2º monitor por uns segundos):
    python ferramentas/umbra_imagens.py
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
SAIDA = os.path.join(RAIZ, "dados", "umbra")
LADO = 384
os.makedirs(SAIDA, exist_ok=True)
os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_FILELOG", "1")

from kivy.config import Config  # noqa: E402

Config.set("graphics", "width", str(LADO))
Config.set("graphics", "height", str(LADO))
Config.set("graphics", "position", "custom")
Config.set("graphics", "left", "2400")
Config.set("graphics", "top", "40")
Config.set("graphics", "resizable", "0")

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402,F401  (cria a janela e o OpenGL antes do desenho)
from kivy.graphics import Callback, Color, Rectangle, RenderContext  # noqa: E402
from kivy.graphics import opengl as gl  # noqa: E402
from kivy.uix.widget import Widget  # noqa: E402
from PIL import Image  # noqa: E402

from widgets.umbra_pintor import FONTE  # noqa: E402

#            estado       boca  olho  inclina feliz torto alerta escuta palpebra dentes
ESTADOS = [("parado",     0.00, 1.00,  0.00, 0.0, 0.0, 0.0, 0.0, 0.08, 0.0),
           ("falando",    0.55, 1.00,  0.00, 0.0, 0.0, 0.0, 0.0, 0.05, 0.3),
           ("ouvindo",    0.14, 1.32, -0.15, 0.0, 0.0, 0.0, 0.0, 0.00, 0.0),
           ("confirmou",  0.08, 1.00, -0.35, 1.0, 0.0, 0.0, 0.0, 0.30, 0.6),
           ("confuso",    0.16, 1.00, -0.20, 0.0, 1.0, 0.0, 0.0, 0.05, 0.0),
           ("alerta",     0.10, 0.80,  0.90, 0.0, 0.0, 1.0, 0.0, 0.00, 1.0)]


class Tela(Widget):
    def __init__(self, **kw):
        self.canvas = RenderContext(use_parent_projection=True, use_parent_modelview=True)
        super().__init__(**kw)
        self.foto = None
        with self.canvas:      # (sem mistura: a cor e a transparência do desenho vão direto para a imagem)
            Callback(lambda i: gl.glBlendFuncSeparate(gl.GL_ONE, gl.GL_ZERO, gl.GL_ONE, gl.GL_ZERO))
            Color(1, 1, 1, 1)
            Rectangle(pos=(0, 0), size=(LADO, LADO))
            Callback(self._ler)

    def _ler(self, instr):
        if self.foto:
            dados = gl.glReadPixels(0, 0, LADO, LADO, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE)
            img = Image.frombytes("RGBA", (LADO, LADO), bytes(dados)).transpose(Image.FLIP_TOP_BOTTOM)
            # o desenho sai com a cor já multiplicada pela transparência; o PNG guarda a cor "pura"
            px = img.load()
            for y in range(LADO):
                for x in range(LADO):
                    r, g, b, a = px[x, y]
                    if 0 < a < 255:
                        px[x, y] = (min(255, r * 255 // a), min(255, g * 255 // a), min(255, b * 255 // a), a)
            img.save(self.foto, optimize=True)
            print("imagem:", os.path.relpath(self.foto, RAIZ))
            self.foto = None
        gl.glBlendFuncSeparate(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA, gl.GL_ONE, gl.GL_ONE)


class Gerador(App):
    def build(self):
        self.tela = Tela(size=(LADO, LADO))
        self.n = 0
        Clock.schedule_interval(self.passo, 0)
        return self.tela

    def passo(self, dt):
        c = self.tela.canvas
        if self.n == 0:
            c.shader.fs = FONTE
            if not c.shader.success:
                print("o desenho não compilou")
                self.stop()
                return False
        i, fase = divmod(self.n, 3)
        self.n += 1
        if i >= len(ESTADOS):
            self.stop()
            return False
        nome, boca, olho, inclina, feliz, torto, alerta, escuta, palpebra, dentes = ESTADOS[i]
        c["u_res"] = [float(LADO), float(LADO)]
        c["u_t"] = 2.0
        for k, v in (("boca", boca), ("olho", olho), ("inclina", inclina), ("feliz", feliz), ("torto", torto),
                     ("alerta", alerta), ("escuta", escuta), ("palpebra", palpebra), ("brilho", 1.0),
                     ("rolar", 0.0), ("enfase", 0.0), ("dentes", dentes)):
            c["u_" + k] = float(v)
        c["u_giro"] = [0.0, 0.0]
        c["u_olhar"] = [0.0, 0.0]
        c.ask_update()
        if fase == 1:
            self.tela.foto = os.path.join(SAIDA, nome + ".png")
        return True


if __name__ == "__main__":
    Gerador().run()
