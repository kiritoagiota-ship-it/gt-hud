"""Peças de interface reaproveitadas entre as telas."""
from kivy.graphics import Color, Ellipse, Line, Mesh, Rectangle
from kivy.metrics import dp
from kivy.properties import ListProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import tema
from widgets.botao import BotaoHUD, _poligono


def soltar(*widgets):
    """Tira cada widget do layout onde está, para remontar a tela em outro
    arranjo (em pé / deitada)."""
    for w in widgets:
        if w.parent is not None:
            w.parent.remove_widget(w)


class PainelHUD(BoxLayout):
    """Caixa por cima do mapa: fundo escuro quase opaco, borda com os cantos
    cortados (mesmo recorte do BotaoHUD)."""
    cor_borda = ListProperty(tema.CIANO)

    def __init__(self, **kw):
        kw.setdefault("padding", dp(10))
        kw.setdefault("spacing", dp(8))
        super().__init__(**kw)
        self.bind(pos=self._d, size=self._d, cor_borda=self._d)

    def _d(self, *a):
        c = min(dp(14), self.height * 0.25)
        pts = _poligono(self.x, self.y, self.width, self.height, c)
        vert = []
        for px, py in pts:
            vert += [px, py, 0, 0]
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*tema.com_alfa(tema.PAINEL, 0.94))
            Mesh(vertices=vert, indices=list(range(len(pts))), mode="triangle_fan")
            Color(*tema.com_alfa(self.cor_borda, 0.9))
            Line(points=[v for p in pts for v in p], close=True, width=dp(1.2))


class Texto(Label):
    """Label que quebra linha e alinha à esquerda."""

    def __init__(self, **kw):
        kw.setdefault("halign", "left")
        kw.setdefault("valign", "middle")
        kw.setdefault("color", tema.BRANCO)
        super().__init__(**kw)
        self.bind(size=lambda *a: setattr(self, "text_size", self.size))


class Cabecalho(BoxLayout):
    """Barra de topo com 'Voltar' e título."""

    def __init__(self, titulo, ao_voltar, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(48))
        kw.setdefault("spacing", dp(12))
        super().__init__(**kw)
        self.add_widget(BotaoHUD(text="Voltar", size_hint_x=None, width=dp(96),
                                 font_size=tema.T_ROTULO + 2,
                                 on_release=lambda *a: ao_voltar()))
        self.titulo = Texto(text=titulo, font_size=tema.T_TITULO, bold=True, color=tema.CIANO)
        self.add_widget(self.titulo)


class Bloco(BoxLayout):
    """Número grande com rótulo pequeno em cima e um traço de acento."""
    rotulo = StringProperty("")
    valor = StringProperty("0")
    cor_acento = ListProperty(tema.CIANO)

    def __init__(self, **kw):
        kw.setdefault("orientation", "vertical")
        kw.setdefault("padding", (dp(14), dp(6), dp(6), dp(6)))
        super().__init__(**kw)
        self._r = Texto(text=self.rotulo, font_size=tema.T_ROTULO, color=tema.CIANO_FRACO,
                        size_hint_y=0.4)
        self._v = Texto(text=self.valor, font_size=tema.T_VALOR, bold=True)
        self.add_widget(self._r)
        self.add_widget(self._v)
        self.bind(rotulo=lambda *a: setattr(self._r, "text", self.rotulo),
                  valor=lambda *a: setattr(self._v, "text", self.valor),
                  pos=self._desenhar, size=self._desenhar, cor_acento=self._desenhar)

    def _desenhar(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*tema.PAINEL)
            Rectangle(pos=self.pos, size=self.size)
            Color(*self.cor_acento)
            Line(points=[self.x + dp(2), self.y + dp(10), self.x + dp(2), self.y + self.height - dp(10)],
                 width=dp(1.5))


class Ponto(Widget):
    """Bolinha de status (GPS)."""
    cor = ListProperty(tema.VERMELHO)

    def __init__(self, **kw):
        kw.setdefault("size_hint", (None, None))
        kw.setdefault("size", (dp(12), dp(12)))
        super().__init__(**kw)
        self.bind(pos=self._d, size=self._d, cor=self._d)
        self._d()

    def _d(self, *a):
        self.canvas.clear()
        with self.canvas:
            Color(*tema.com_alfa(self.cor, 0.25))
            Ellipse(pos=(self.x - dp(3), self.y - dp(3)),
                    size=(self.width + dp(6), self.height + dp(6)))
            Color(*self.cor)
            Ellipse(pos=self.pos, size=self.size)


class ItemViagem(ButtonBehavior, BoxLayout):
    """Linha da lista de viagens."""

    def __init__(self, titulo, detalhe, **kw):
        kw.setdefault("orientation", "vertical")
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(74))
        kw.setdefault("padding", (dp(14), dp(8)))
        super().__init__(**kw)
        self.add_widget(Texto(text=titulo, font_size=tema.T_BOTAO, bold=True))
        self.add_widget(Texto(text=detalhe, font_size=tema.T_ROTULO + 1, color=tema.CIANO_FRACO))
        self.bind(pos=self._d, size=self._d, state=self._d)
        self._d()

    def _d(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*(tema.com_alfa(tema.CIANO, 0.18) if self.state == "down" else tema.PAINEL))
            Rectangle(pos=self.pos, size=self.size)
            Color(*tema.com_alfa(tema.CIANO, 0.5))
            Line(points=[self.x, self.y + dp(1), self.x + self.width, self.y + dp(1)],
                 width=dp(1))
