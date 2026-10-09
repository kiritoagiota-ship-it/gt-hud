"""Peças de interface reaproveitadas entre as telas."""
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import (Color, Ellipse, InstructionGroup, Line, PopMatrix, PushMatrix, Rectangle,
                           RoundedRectangle, Scale)
from kivy.metrics import dp
from kivy.properties import ListProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import tema
from widgets.botao import BotaoHUD, _poligono, cantos, degrade, malha_degrade, mexer, vibrar_toque

FECHA_JANELA_S = 0.12     # a janela encolhe e some ao fechar (0 = fecha de estalo, como antes)
AVISO_SAI_S = 0.30        # o aviso curto se apaga em vez de sumir de estalo


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
        plano = [v for p in pts for v in p]
        self.canvas.before.clear()
        with self.canvas.before:
            if tema.monarca():   # a "aura" roxa por trás da janela do sistema
                Color(*tema.com_alfa(tema.ROXO, 0.13))
                Line(points=plano, close=True, width=dp(7.5), joint="round")
                Color(*tema.com_alfa(tema.ROXO, 0.22))
                Line(points=plano, close=True, width=dp(4.4), joint="round")
            Color(*tema.com_alfa(self.cor_borda, 0.10))            # halo
            Line(points=plano, close=True, width=dp(3.6), joint="round")
            Color(*tema.com_alfa(tema.PAINEL_CLARO, 0.96))         # corpo em degradê
            malha_degrade(pts, self.y, self.height)
            Color(*tema.com_alfa(self.cor_borda, 0.9))
            Line(points=plano, close=True, width=dp(1.2))
            for traco in cantos(pts, c):                           # cantos marcados
                Line(points=traco, width=dp(2.2), cap="square", joint="miter")


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
        self.bind(pos=self._d, size=self._d)

    def _d(self, *a):
        # risco de HUD embaixo do título: forte à esquerda, sumindo à direita
        self.canvas.after.clear()
        y, x0 = self.y - dp(4), self.x + dp(108)
        with self.canvas.after:
            Color(*tema.CIANO)
            Line(points=[x0, y, x0 + dp(46), y], width=dp(1.6), cap="none")
            Color(*tema.com_alfa(tema.CIANO, 0.28))
            Line(points=[x0 + dp(52), y, self.right, y], width=dp(1))


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
            Color(*tema.PAINEL_CLARO)
            Rectangle(pos=self.pos, size=self.size, texture=degrade())
            Color(*tema.com_alfa(self.cor_acento, 0.35))            # risco fino em cima
            Line(points=[self.x, self.top, self.right, self.top], width=dp(1))
            barra = [self.x + dp(2), self.y + dp(10), self.x + dp(2), self.y + self.height - dp(10)]
            Color(*tema.com_alfa(self.cor_acento, 0.22))            # acento com brilho
            Line(points=barra, width=dp(4))
            Color(*self.cor_acento)
            Line(points=barra, width=dp(1.6))


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
        # uma linha cada, com "..." no fim: nome comprido quebrava em duas
        # linhas e invadia a de baixo (texto desalinhado)
        self.add_widget(Texto(text=titulo, font_size=tema.T_BOTAO, bold=True,
                              shorten=True, shorten_from="right", max_lines=1))
        self.add_widget(Texto(text=detalhe, font_size=tema.T_ROTULO + 1, color=tema.CIANO_FRACO,
                              shorten=True, shorten_from="right", max_lines=1))
        self.bind(pos=self._d, size=self._d, state=self._d)
        self._d()

    def on_press(self):
        vibrar_toque()

    def _d(self, *a):
        tocado = self.state == "down"
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*tema.PAINEL_CLARO)
            Rectangle(pos=self.pos, size=self.size, texture=degrade())
            if tocado:
                Color(*tema.com_alfa(tema.CIANO, 0.22))
                Rectangle(pos=self.pos, size=self.size)
            Color(*tema.com_alfa(tema.CIANO, 0.45))
            Line(points=[self.x, self.y + dp(1), self.x + self.width, self.y + dp(1)],
                 width=dp(1))
            # acento à esquerda (acende no toque)
            Color(*tema.com_alfa(tema.CIANO, 1.0 if tocado else 0.55))
            Line(points=[self.x + dp(2), self.y + dp(12), self.x + dp(2), self.top - dp(12)],
                 width=dp(1.6))


class Aviso(Texto):
    """Mensagem curta por cima do mapa ("Link pronto", "Viagem salva"...): uma
    pílula escura do tamanho do texto, com a borda na cor da mensagem, que
    aparece suave. (Antes era só o texto solto: em cima de rua clara sumia.)"""

    def __init__(self, **kw):
        kw.setdefault("halign", "center")
        super().__init__(**kw)
        self.bind(text=self._mudou, texture_size=self._d, pos=self._d, size=self._d, color=self._d)

    def _mudou(self, *a):
        Animation.cancel_all(self, "opacity")
        if self.text:   # entra subindo um pouco enquanto aparece
            sobe = mexer(self)[0]
            Animation.cancel_all(sobe)
            self.opacity, sobe.y = 0.0, -dp(14)
            Animation(opacity=1.0, d=0.2, t="out_quad").start(self)
            Animation(y=0.0, d=0.26, t="out_cubic").start(sobe)
        self._d()

    def firmar(self):
        """Vai mostrar de novo (talvez o mesmo texto): desiste de sair, se estava saindo."""
        Animation.cancel_all(self, "opacity")
        if self.text:
            self.opacity = 1.0

    def sair(self):
        """Some se apagando (e só então o texto sai)."""
        if not self.text:
            return
        Animation.cancel_all(self, "opacity")
        if AVISO_SAI_S <= 0:
            self.text = ""
            return
        saida = Animation(opacity=0.0, d=AVISO_SAI_S, t="in_quad")
        saida.bind(on_complete=lambda *a: setattr(self, "text", ""))
        saida.start(self)

    def _d(self, *a):
        self.canvas.before.clear()
        if not self.text:
            return
        w = min(self.width, self.texture_size[0] + dp(24))
        h = min(self.height, self.texture_size[1] + dp(12))
        x, y = self.center_x - w / 2.0, self.center_y - h / 2.0
        with self.canvas.before:
            Color(*tema.com_alfa(tema.FUNDO, 0.90))
            RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(10)])
            Color(*tema.com_alfa(self.color, 0.75))
            Line(rounded_rectangle=(x, y, w, h, dp(10)), width=dp(1.1))


def entrar(conteudo, segundos=0.16, subir=0.0):
    """Entrada suave do conteúdo de uma tela (aparece em vez de "piscar").
    subir > 0: além de aparecer, sobe esses px até o lugar (telas de lista)."""
    Animation.cancel_all(conteudo, "opacity", "y")
    conteudo.opacity = 0.0
    if subir:
        conteudo.y = -subir
        Animation(opacity=1.0, y=0, d=segundos, t="out_cubic").start(conteudo)
    else:
        Animation(opacity=1.0, d=segundos, t="out_quad").start(conteudo)


def abrir_janela(janela):
    """Abre a janelinha (Popup) com a cara do app e uma entrada animada (pedido do dono,
    08/10/2026: \"uma animaçãozinha para abrir esses pop-ups\"): ela cresce de 86% até o
    tamanho, passando um tiquinho, enquanto aparece; e ganha a borda de cantos cortados dos
    painéis (com a aura roxa no tema Monarca), em vez de um retângulo liso."""
    escala = Scale(0.86, 0.86, 1)
    borda = InstructionGroup()
    janela.canvas.before.add(PushMatrix())
    janela.canvas.before.add(escala)
    janela.canvas.after.add(borda)
    janela.canvas.after.add(PopMatrix())

    def desenhar(*a):
        escala.origin = janela.center
        borda.clear()
        c = dp(14)
        pts = _poligono(janela.x, janela.y, janela.width, janela.height, c)
        plano = [v for p in pts for v in p]
        if tema.monarca():
            borda.add(Color(*tema.com_alfa(tema.ROXO, 0.16)))
            borda.add(Line(points=plano, close=True, width=dp(7), joint="round"))
        borda.add(Color(*tema.com_alfa(tema.CIANO, 0.9)))
        borda.add(Line(points=plano, close=True, width=dp(1.3)))
        for traco in cantos(pts, c):
            borda.add(Line(points=traco, width=dp(2.4), cap="square", joint="miter"))
    janela.bind(pos=desenhar, size=desenhar)
    # ... e fecha encolhendo e se apagando (pedido do dono, 09/10/2026), em vez de sumir de estalo
    fechar_de_vez = janela.dismiss
    fechando = []

    def fechar(*a, **kw):
        if fechando:
            return
        if FECHA_JANELA_S <= 0:
            fechar_de_vez(*a, **kw)
            return
        fechando.append(True)
        Animation.cancel_all(janela, "opacity")
        Animation.cancel_all(escala)
        saida = Animation(opacity=0.0, d=FECHA_JANELA_S, t="in_quad")
        saida.bind(on_complete=lambda *x: fechar_de_vez(animation=False))
        saida.start(janela)
        Animation(x=0.9, y=0.9, d=FECHA_JANELA_S, t="in_quad").start(escala)
    janela.dismiss = fechar
    # escolheu uma opção que FAZ algo (abre outra janela, troca de tela): esta sai na hora, senão
    # as duas animações se atropelam (a 1.0.69 fazia isso e o dono achou estranho). A saída
    # animada fica para o "Fechar"/"Cancelar" e o toque fora.
    janela.fechar_ja = lambda: None if fechando else fechar_de_vez(animation=False)
    janela.opacity = 0.0
    janela.open()
    desenhar()
    Animation(opacity=1.0, d=0.16, t="out_quad").start(janela)
    Animation(x=1.0, y=1.0, d=0.26, t="out_back").start(escala)
    return janela


def escolher(titulo, opcoes, texto="", altura_texto=None):
    """Janelinha com um botão por opção: opcoes = [(rótulo, função ou None), ...]
    (None só fecha). Devolve a janela. `altura_texto`: para um texto mais longo que 4 linhas."""
    from kivy.uix.popup import Popup
    from widgets.botao import BotaoHUD

    caixa = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(4))
    altura = dp(64) + len(opcoes) * dp(56)
    if texto:
        altura_texto = altura_texto or dp(96)
        aviso = Texto(text=texto, font_size=tema.T_ROTULO + 2, size_hint_y=None, height=altura_texto,
                      halign="left", valign="top")
        aviso.bind(size=lambda w, s: setattr(w, "text_size", s))
        caixa.add_widget(aviso)
        altura += altura_texto + dp(8)
    janela = Popup(title=titulo, content=caixa, size_hint=(0.92, None), height=altura,
                   title_color=tema.CIANO, title_size=tema.T_BOTAO, separator_color=tema.CIANO,
                   background="", background_color=tema.PAINEL, auto_dismiss=True)

    def tocar(funcao):
        if funcao is None:
            janela.dismiss()
            return
        janela.fechar_ja()
        funcao()
    janela.botoes = []
    for k, (rotulo, funcao) in enumerate(opcoes):
        b = BotaoHUD(text=rotulo, destaque=(k == 0 and funcao is not None), font_size=tema.T_ROTULO + 2,
                     size_hint_y=None, height=dp(48), on_release=lambda w, f=funcao: tocar(f))
        janela.botoes.append(b)
        caixa.add_widget(b)
    abrir_janela(janela)
    return janela


def pedir_nome(ao_confirmar, sugestao="", titulo="Nome do lugar", botao="Salvar",
               dica="Ex.: Barbearia do amigo", limite=60):
    """Janelinha que pergunta um texto curto (o nome de um lugar);
    ao_confirmar(texto) só é chamado com o campo preenchido. O campo já vem
    com a sugestão, selecionada (digitar por cima troca)."""
    from kivy.uix.popup import Popup
    from kivy.uix.textinput import TextInput
    from widgets.botao import BotaoHUD

    caixa = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(4))
    campo = TextInput(text=sugestao or "", hint_text=dica, multiline=False,
                      font_size=tema.T_BOTAO, size_hint_y=None, height=dp(48),
                      background_normal="", background_active="", background_color=tema.FUNDO,
                      foreground_color=tema.BRANCO, hint_text_color=tema.CIANO_FRACO,
                      cursor_color=tema.CIANO, padding=(dp(10), dp(12)), write_tab=False)
    botoes = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    janela = Popup(title=titulo, content=caixa, size_hint=(0.92, None), height=dp(210),
                   title_color=tema.CIANO, title_size=tema.T_BOTAO, separator_color=tema.CIANO,
                   background="", background_color=tema.PAINEL, auto_dismiss=True)

    def confirmar(*a):
        nome = campo.text.strip()[:limite]
        if not nome:
            campo.focus = True
            return
        janela.fechar_ja()
        ao_confirmar(nome)

    botoes.add_widget(BotaoHUD(text="Cancelar", font_size=tema.T_ROTULO + 2,
                               on_release=lambda *a: janela.dismiss()))
    botoes.add_widget(BotaoHUD(text=botao, destaque=True, font_size=tema.T_ROTULO + 2,
                               on_release=confirmar))
    campo.bind(on_text_validate=confirmar)
    caixa.add_widget(campo)
    caixa.add_widget(botoes)
    abrir_janela(janela)
    campo.focus = True
    if sugestao:
        Clock.schedule_once(lambda dt: campo.select_all(), 0.1)
    janela.campo, janela.confirmar = campo, confirmar   # para os testes de tela
    return janela
