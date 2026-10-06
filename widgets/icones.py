"""Ícones dos botões do mapa, desenhados em traço (as fontes do app não têm
esses símbolos, e emoji não renderiza). Um ícone lê mais rápido que uma
palavra com a bike andando.

desenhar(nome, cx, cy, tam, cor): chamar DENTRO de um `with canvas:`.
"""
import math

from kivy.graphics import Color, Ellipse, Line
from kivy.metrics import dp


def desenhar(nome, cx, cy, tam, cor):
    r = tam / 2.0
    grosso = max(dp(1.6), tam * 0.085)
    Color(*cor)
    if nome == "mais":
        Line(points=[cx - r * 0.7, cy, cx + r * 0.7, cy], width=grosso, cap="round")
        Line(points=[cx, cy - r * 0.7, cx, cy + r * 0.7], width=grosso, cap="round")
    elif nome == "menos":
        Line(points=[cx - r * 0.7, cy, cx + r * 0.7, cy], width=grosso, cap="round")
    elif nome == "centralizar":
        # mira: círculo, quatro riscos e o ponto no meio
        Line(circle=(cx, cy, r * 0.62), width=grosso)
        for ang in (0, 90, 180, 270):
            a = math.radians(ang)
            Line(points=[cx + math.cos(a) * r * 0.62, cy + math.sin(a) * r * 0.62,
                         cx + math.cos(a) * r * 1.0, cy + math.sin(a) * r * 1.0], width=grosso, cap="round")
        d = r * 0.36
        Ellipse(pos=(cx - d / 2, cy - d / 2), size=(d, d))
    elif nome == "rotas":
        # um caminho que se divide em dois
        base, meio = (cx, cy - r * 0.95), (cx, cy - r * 0.15)
        for lado in (-1, 1):
            ponta = (cx + lado * r * 0.8, cy + r * 0.85)
            Line(points=[base[0], base[1], meio[0], meio[1], ponta[0], ponta[1]],
                 width=grosso, cap="round", joint="round")
            d = r * 0.42
            Ellipse(pos=(ponta[0] - d / 2, ponta[1] - d / 2), size=(d, d))
    elif nome == "vivo":
        # antena transmitindo: ponto com ondas dos dois lados
        d = r * 0.5
        Ellipse(pos=(cx - d / 2, cy - d / 2), size=(d, d))
        for raio in (r * 0.62, r * 1.0):
            Line(circle=(cx, cy, raio, 50, 130), width=grosso, cap="round")     # direita
            Line(circle=(cx, cy, raio, 230, 310), width=grosso, cap="round")    # esquerda


NOMES = ("mais", "menos", "centralizar", "rotas", "vivo")
