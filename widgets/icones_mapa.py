"""Emblemas dos lugares no mapa (pedido do dono em 07/10/2026: "ícones bonitos
e interativos"): um disco na cor da categoria com um desenho branco dentro
(bomba de posto, cruz de farmácia, carrinho de mercado, talheres...), feito
só com formas simples (a fonte do app não tem esses símbolos e emoji não
desenha no Kivy do celular).

qual_icone(grupo, texto) escolhe o desenho pelo nome/legenda do lugar;
emblema(icone, cor) devolve as instruções, centradas em (0, 0), com raio RAIO.
"""
import math
import unicodedata

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Ellipse, InstructionGroup, Line, Mesh, Rectangle
from kivy.metrics import dp, sp

RAIO = 10.5   # dp

# (desenho, palavras que o denunciam no nome ou na legenda, sem acento)
_PISTAS = (
    ("posto", ("posto", "combustivel", "gasolina")),
    ("farmacia", ("farmac", "drogar", "drogasil", "pague menos")),
    ("hospital", ("hospital", "upa ", "cais ", "ciams", "pronto socorro", "maternidade", "clinica", "saude")),
    ("mercado", ("mercado", "supermerc", "atacad", "hiper", "mercearia", "feira", "conveniencia", "acougue")),
    ("cafe", ("padaria", "panific", "cafe", "confeitaria", "sorvet", "acai")),
    ("bar", ("bar ", "boteco", "pub", "chopp", "cervej", "distribuidora", "bebidas")),
    ("comida", ("restaurante", "pizz", "churras", "lanch", "burger", "pastel", "espet", "sushi", "pamonh",
                "galeteria", "pit dog", "comida")),
    ("banco", ("banco", "caixa economica", "sicoob", "sicredi", "bradesco", "itau", "santander", "loterica", "loter")),
    ("escola", ("escola", "colegio", "faculdade", "universidade", "cmei", "creche", "senai", "senac", "instituto",
                "biblioteca", "curso")),
    ("igreja", ("igreja", "paroquia", "capela", "catedral", "templo", "assembleia", "congregacao", "santuario")),
    ("hotel", ("hotel", "pousada", "motel", "hostel")),
    ("oficina", ("oficina", "mecanic", "borrach", "auto pecas", "autopecas", "auto center", "funilaria", "lava jato",
                 "lava-jato", "bicicletaria", "motos", "veiculos")),
    ("esporte", ("academia", "quadra", "campo", "estadio", "ginasio", "esporte", "crossfit", "arena")),
    ("onibus", ("terminal", "rodoviaria", "onibus", "estacao")),
    ("praca", ("praca", "parque", "bosque", "jardim", "parquinho")),
    ("salao", ("salao", "barbearia", "barber", "cabeleireir", "estetica", "beleza")),
    ("policia", ("policia", "delegacia", "batalhao", "bombeiro", "guarda")),
)
_DO_GRUPO = {"praca": "praca", "comida": "comida", "compras": "loja", "saude": "hospital", "ensino": "escola",
             "servico": "ponto", "lazer": "estrela", "outros": "ponto"}
NOMES = {"posto": "Posto de combustível", "farmacia": "Farmácia", "hospital": "Saúde", "mercado": "Mercado",
         "cafe": "Padaria ou café", "bar": "Bar", "comida": "Restaurante ou lanchonete", "banco": "Banco",
         "escola": "Ensino", "igreja": "Igreja ou templo", "hotel": "Hospedagem", "oficina": "Oficina ou veículos",
         "esporte": "Esporte", "onibus": "Ônibus", "praca": "Praça ou parque", "salao": "Salão ou barbearia",
         "policia": "Segurança", "loja": "Loja", "estrela": "Lazer", "ponto": "Lugar"}


def _limpo(texto):
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn") + " "


def qual_icone(grupo, texto):
    """O desenho do lugar: pelas palavras do nome/legenda; senão, o do grupo."""
    t = _limpo(texto)
    for icone, pistas in _PISTAS:
        if any(p in t for p in pistas):
            return icone
    return _DO_GRUPO.get(grupo, "ponto")


def _tri(g, pontos):
    g.add(Mesh(vertices=[v for x, y in pontos for v in (x, y, 0, 0)], indices=list(range(len(pontos))),
               mode="triangle_fan"))


def _letra(g, texto, tamanho=12.5):
    rotulo = CoreLabel(text=texto, font_size=sp(tamanho), bold=True)
    rotulo.refresh()
    w, h = rotulo.texture.size
    g.add(Rectangle(texture=rotulo.texture, size=(w, h), pos=(-w / 2.0, -h / 2.0)))


def _desenho(g, icone):
    """O símbolo branco, numa área de ~13 x 13 dp em volta de (0, 0)."""
    u = dp(1)
    if icone == "posto":            # bomba: corpo, visor e mangueira
        g.add(Rectangle(pos=(-5 * u, -6 * u), size=(7 * u, 12 * u)))
        g.add(Line(points=[2 * u, 2 * u, 5 * u, 2 * u, 5 * u, -4 * u], width=1.1 * u, cap="square"))
        g.add(Color(0, 0, 0, 0.45))
        g.add(Rectangle(pos=(-3.5 * u, 1 * u), size=(4 * u, 3.2 * u)))
    elif icone == "farmacia":       # cruz
        g.add(Rectangle(pos=(-2 * u, -6 * u), size=(4 * u, 12 * u)))
        g.add(Rectangle(pos=(-6 * u, -2 * u), size=(12 * u, 4 * u)))
    elif icone == "hospital":
        _letra(g, "H")
    elif icone == "banco":
        _letra(g, "$")
    elif icone == "mercado":        # carrinho: cesto, alça e rodas
        _tri(g, [(-5 * u, 4 * u), (6 * u, 4 * u), (4.5 * u, -2 * u), (-3.5 * u, -2 * u)])
        g.add(Line(points=[-7 * u, 6 * u, -5 * u, 4 * u], width=1.0 * u))
        g.add(Ellipse(pos=(-4 * u, -6.2 * u), size=(3 * u, 3 * u)))
        g.add(Ellipse(pos=(2 * u, -6.2 * u), size=(3 * u, 3 * u)))
    elif icone == "comida":         # garfo e faca
        for dx in (-5.2, -3.6, -2.0):
            g.add(Rectangle(pos=(dx * u, 1 * u), size=(0.9 * u, 5.5 * u)))
        g.add(Rectangle(pos=(-5.2 * u, 0), size=(4.1 * u, 1.6 * u)))
        g.add(Rectangle(pos=(-4.1 * u, -6.5 * u), size=(1.6 * u, 7 * u)))
        _tri(g, [(2.2 * u, 6.5 * u), (5 * u, 3 * u), (5 * u, -0.5 * u), (2.2 * u, -0.5 * u)])
        g.add(Rectangle(pos=(2.2 * u, -6.5 * u), size=(1.6 * u, 6.5 * u)))
    elif icone == "cafe":           # xícara com alça e pires
        g.add(Rectangle(pos=(-5.5 * u, -3 * u), size=(8 * u, 7 * u)))
        g.add(Line(circle=(3.2 * u, 1 * u, 2.6 * u), width=1.0 * u))
        g.add(Rectangle(pos=(-6.5 * u, -5.8 * u), size=(11 * u, 1.5 * u)))
    elif icone == "bar":            # taça
        _tri(g, [(-5.5 * u, 6 * u), (5.5 * u, 6 * u), (0, -0.5 * u)])
        g.add(Rectangle(pos=(-0.8 * u, -5 * u), size=(1.6 * u, 5 * u)))
        g.add(Rectangle(pos=(-3.5 * u, -6.3 * u), size=(7 * u, 1.5 * u)))
    elif icone == "escola":         # capelo de formatura
        _tri(g, [(0, 5.5 * u), (7 * u, 1.5 * u), (0, -2.5 * u), (-7 * u, 1.5 * u)])
        g.add(Rectangle(pos=(-3.5 * u, -5.5 * u), size=(7 * u, 3 * u)))
    elif icone == "igreja":         # cruz latina
        g.add(Rectangle(pos=(-1.4 * u, -6.5 * u), size=(2.8 * u, 13 * u)))
        g.add(Rectangle(pos=(-4.5 * u, 1.2 * u), size=(9 * u, 2.8 * u)))
    elif icone == "hotel":          # cama
        g.add(Rectangle(pos=(-6.5 * u, -5 * u), size=(1.8 * u, 10 * u)))
        g.add(Rectangle(pos=(-6.5 * u, -3.2 * u), size=(13 * u, 3.2 * u)))
        g.add(Rectangle(pos=(4.7 * u, -5 * u), size=(1.8 * u, 4 * u)))
        g.add(Ellipse(pos=(-4 * u, 0.6 * u), size=(3.6 * u, 3.6 * u)))
    elif icone == "oficina":        # chave de boca
        g.add(Line(points=[-4 * u, -4 * u, 2.5 * u, 2.5 * u], width=1.6 * u, cap="round"))
        g.add(Line(circle=(3.6 * u, 3.6 * u, 2.6 * u, 100, 350), width=1.3 * u))
    elif icone == "esporte":        # bola
        g.add(Line(circle=(0, 0, 5.6 * u), width=1.2 * u))
        g.add(Line(points=[-5.6 * u, 0, 5.6 * u, 0], width=0.9 * u))
        g.add(Line(points=[0, -5.6 * u, 0, 5.6 * u], width=0.9 * u))
    elif icone == "onibus":         # ônibus de frente
        g.add(Rectangle(pos=(-5.5 * u, -4 * u), size=(11 * u, 10.5 * u)))
        g.add(Ellipse(pos=(-5 * u, -6.5 * u), size=(3.2 * u, 3.2 * u)))
        g.add(Ellipse(pos=(1.8 * u, -6.5 * u), size=(3.2 * u, 3.2 * u)))
        g.add(Color(0, 0, 0, 0.45))
        g.add(Rectangle(pos=(-4 * u, 0.5 * u), size=(8 * u, 4 * u)))
    elif icone == "praca":          # árvore
        g.add(Ellipse(pos=(-5.5 * u, -1.5 * u), size=(11 * u, 9 * u)))
        g.add(Rectangle(pos=(-1.1 * u, -6.5 * u), size=(2.2 * u, 6 * u)))
    elif icone == "salao":          # tesoura
        g.add(Line(points=[-4.5 * u, 6 * u, 3 * u, -2.5 * u], width=1.0 * u))
        g.add(Line(points=[4.5 * u, 6 * u, -3 * u, -2.5 * u], width=1.0 * u))
        g.add(Line(circle=(-3.8 * u, -4.2 * u, 2.0 * u), width=1.0 * u))
        g.add(Line(circle=(3.8 * u, -4.2 * u, 2.0 * u), width=1.0 * u))
    elif icone == "policia":        # escudo
        _tri(g, [(0, 6.5 * u), (5.5 * u, 4.5 * u), (5.5 * u, -0.5 * u), (0, -6.5 * u),
                 (-5.5 * u, -0.5 * u), (-5.5 * u, 4.5 * u)])
    elif icone == "loja":           # sacola
        g.add(Rectangle(pos=(-5 * u, -6 * u), size=(10 * u, 8.5 * u)))
        g.add(Line(circle=(0, 2.5 * u, 3 * u, -90, 90), width=1.0 * u))
    elif icone == "estrela":
        pontos = []
        for k in range(10):
            r = (6.5 if k % 2 == 0 else 2.8) * u
            a = math.pi / 2 + k * math.pi / 5
            pontos.append((r * math.cos(a), r * math.sin(a)))
        _tri(g, [(0, 0)] + pontos + [pontos[0]])
    else:                           # "ponto": um lugar qualquer
        g.add(Ellipse(pos=(-3 * u, -3 * u), size=(6 * u, 6 * u)))


def emblema(icone, cor, fundo):
    """Disco na cor `cor` com aro `fundo` e o desenho branco: InstructionGroup."""
    g = InstructionGroup()
    r = dp(RAIO)
    g.add(Color(0, 0, 0, 0.28))                                     # sombra: solta o emblema do mapa
    g.add(Ellipse(pos=(-r - dp(1), -r - dp(2.5)), size=(2 * r + dp(2), 2 * r + dp(2))))
    g.add(Color(*fundo[:3], 1))
    g.add(Ellipse(pos=(-r - dp(1.6), -r - dp(1.6)), size=(2 * r + dp(3.2), 2 * r + dp(3.2))))
    g.add(Color(cor[0] * 0.78, cor[1] * 0.78, cor[2] * 0.78, 1))     # fecha a cor: o branco aparece em cima
    g.add(Ellipse(pos=(-r, -r), size=(2 * r, 2 * r)))
    g.add(Color(1, 1, 1, 1))
    _desenho(g, icone)
    return g
