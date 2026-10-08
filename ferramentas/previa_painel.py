"""Prévia do painel flutuante no PC (o painel de verdade é Java e só roda no
celular). Repete, com a biblioteca de imagens, as MESMAS medidas, cores e
contas do PainelFlutuante.java, com ruas e rota de verdade (dos arquivos de
mapa dos testes). Serve para conferir o layout antes de mandar compilar.

    python ferramentas/previa_painel.py        -> ferramentas/testes_tela/fotos_painel/
"""
import glob
import math
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import caminhos  # noqa: E402,F401  (as pastas do código no caminho de busca)
os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_LOG_MODE", "PYTHON")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import mini_mapa  # noqa: E402
import rota as rotas  # noqa: E402
import segundo_plano  # noqa: E402
from navegacao import Navegacao  # noqa: E402

E = 3                      # pixels por "u" (dp) na prévia
LARGURA, ALTURA = 340, 166
FRENTE, ATRAS = 230.0, 70.0


def fonte(tam, negrito=True):
    return ImageFont.truetype(r"C:\Windows\Fonts\%s" % ("arialbd.ttf" if negrito else "arial.ttf"), int(tam * E))


def cortado(x0, y0, x1, y1, c):
    return [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]


def painel(claro, textos, pontos, inicio, aqui, ruas, alerta=0):
    u = E
    w, h = LARGURA * u, ALTURA * u
    destaque = (0, 120, 143) if claro else (25, 227, 255)
    forte = (10, 26, 36) if claro else (242, 251, 255)
    suave = (63, 98, 114) if claro else (169, 220, 234)
    cor_mapa = (227, 234, 239) if claro else (10, 19, 29)
    cor_rua = (255, 255, 255) if claro else (36, 54, 74)
    cor_rua_grande = (255, 233, 168) if claro else (47, 70, 95)
    borda = ((208, 31, 64) if claro else (255, 51, 85)) if alerta >= 2 else (
        ((200, 90, 0) if claro else (255, 138, 0)) if alerta == 1 else destaque)
    base = Image.new("RGB", (w, h), (205, 210, 216) if claro else (22, 26, 36))
    cam = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(cam)
    m = 7 * u
    mold = cortado(m, m, w - m, h - m, 15 * u)
    d.line(mold + [mold[0]], fill=borda + (0x26,), width=11 * u, joint="curve")
    d.line(mold + [mold[0]], fill=borda + (0x50,), width=6 * u, joint="curve")
    d.polygon(mold, fill=(245, 250, 252, 250) if claro else (9, 16, 26, 245))
    d.line(mold + [mold[0]], fill=borda + (255,), width=int(2.2 * u))
    # mini mapa
    qx = qy = m + 9 * u
    lado = h - 2 * (m + 9 * u)
    caixa = cortado(qx, qy, qx + lado, qy + lado, 9 * u)
    mapa = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dm = ImageDraw.Draw(mapa)
    dm.polygon(caixa, fill=cor_mapa + (255,))
    escala = lado / (FRENTE + ATRAS)
    ox, oy = qx + lado * 0.56, qy + lado - ATRAS * escala
    ac = [0.0]
    for a, b in zip(pontos, pontos[1:]):
        ac.append(ac[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))

    def ponto_em(s):
        s = max(0.0, min(ac[-1], s))
        i = 0
        while i < len(ac) - 2 and ac[i + 1] < s:
            i += 1
        t = ac[i + 1] - ac[i]
        f = (s - ac[i]) / t if t else 0.0
        return pontos[i][0] + (pontos[i + 1][0] - pontos[i][0]) * f, pontos[i][1] + (pontos[i + 1][1] - pontos[i][1]) * f
    s = aqui - inicio
    px, py = ponto_em(s)
    ax, ay = ponto_em(s - 4)
    bx_, by_ = ponto_em(s + 14)
    ux, uy = bx_ - ax, by_ - ay
    t = math.hypot(ux, uy) or 1.0
    ux, uy = ux / t, uy / t

    def tela(x, y):
        dx, dy = x - px, y - py
        return ox + (dx * uy - dy * ux) * escala, oy - (dx * ux + dy * uy) * escala
    for g in (1, 2, 3):
        for grossura, pts in ruas:
            if grossura == g:
                dm.line([tela(*p) for p in pts], fill=(cor_rua_grande if g >= 3 else cor_rua) + (255,),
                        width=int((3.2 + 1.9 * g) * u), joint="curve")
    linha = [tela(*p) for p in pontos]
    dm.line(linha, fill=destaque + (0x40,), width=11 * u, joint="curve")
    dm.line(linha, fill=destaque + (255,), width=int(5.2 * u), joint="curve")
    s9 = 10 * u
    seta = [(ox, oy - s9 * 1.35), (ox + s9 * 0.9, oy + s9 * 0.85), (ox, oy + s9 * 0.3), (ox - s9 * 0.9, oy + s9 * 0.85)]
    dm.polygon(seta, fill=(255, 255, 255, 255) if claro else (7, 17, 27, 255))
    dm.line(seta + [seta[0]], fill=destaque + (255,), width=int(2.4 * u), joint="curve")
    mascara = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mascara).polygon(caixa, fill=255)
    cam.paste(mapa, (0, 0), Image.composite(mapa.getchannel("A"), Image.new("L", (w, h), 0), mascara))
    d = ImageDraw.Draw(cam)
    d.line(caixa + [caixa[0]], fill=destaque + (0xA0,), width=max(1, int(1.2 * u)))
    cx, cy, br = qx + 19 * u, qy + 19 * u, 11 * u
    d.ellipse((cx - br, cy - br, cx + br, cy + br), fill=cor_mapa + (0xE0,), outline=destaque + (0xC0,), width=max(1, int(1.3 * u)))
    ang = -math.atan2(ux, uy)

    def gira(x, y):
        return cx + x * math.cos(ang) - y * math.sin(ang), cy + x * math.sin(ang) + y * math.cos(ang)
    d.polygon([gira(0, -br * 0.72), gira(br * 0.3, 0), gira(0, br * 0.72), gira(-br * 0.3, 0)], fill=destaque + (0x70,))
    d.polygon([gira(0, -br * 0.72), gira(br * 0.3, 0), gira(-br * 0.3, 0)], fill=destaque + (255,))
    # direita
    x = qx + lado + 14 * u
    fim = w - m - 12 * u
    larg = fim - x
    d.line([(x - 6 * u, qy + 8 * u), (x + 2 * u, qy), (x + larg * 0.55, qy), (x + larg * 0.55 + 7 * u, qy + 7 * u),
            (fim + 2 * u, qy + 7 * u)], fill=destaque + (0x80,), width=max(1, int(1.1 * u)))
    for (x0, y0, x1, y1, alfa) in ((fim - 16 * u, qy + 11 * u, fim - 9 * u, qy + 18 * u, 255),
                                   (fim - 9 * u, qy + 11 * u, fim - 2 * u, qy + 18 * u, 0x90),
                                   (fim - 12 * u, h - m - 5 * u, fim + 1 * u, h - m - 18 * u, 0x90),
                                   (fim - 4 * u, h - m - 5 * u, fim + 1 * u, h - m - 10 * u, 255)):
        d.line([(x0, y0), (x1, y1)], fill=destaque + (alfa,), width=int(2.4 * u))
    distancia, instrucao, rua, vel, resto = textos
    numero, unidade = (distancia.rsplit(" ", 1) + [""])[:2] if distancia[:1].isdigit() else (distancia, "")
    f33 = fonte(32)
    d.text((x, qy + 37 * u), numero, font=f33, fill=forte + (255,), anchor="ls")
    d.text((x + d.textlength(numero, font=f33) + 5 * u, qy + 37 * u), unidade, font=f33, fill=suave + (255,), anchor="ls")
    d.text((x, qy + 58 * u), instrucao, font=fonte(16), fill=forte + (255,), anchor="ls")
    d.text((x, qy + 76 * u), rua, font=fonte(14), fill=destaque + (255,), anchor="ls")
    f31 = fonte(28)
    cor_vel = borda if alerta >= 1 else destaque
    d.text((x, qy + 106 * u), vel, font=f31, fill=cor_vel + (255,), anchor="ls")
    d.text((x + d.textlength(vel, font=f31) + 6 * u, qy + 106 * u), "km/h", font=fonte(14), fill=suave + (255,), anchor="ls")
    y_risco = qy + 113 * u
    d.line([(x - 4 * u, y_risco), (fim - 14 * u, y_risco)], fill=destaque + (0xA0,), width=max(1, int(1.1 * u)))
    rx, ry, raio = x + 7 * u, qy + lado - 9 * u, 6 * u
    d.ellipse((rx - raio, ry - raio, rx + raio, ry + raio), outline=destaque + (255,), width=int(1.6 * u))
    d.line([(rx, ry), (rx, ry - raio * 0.6)], fill=destaque + (255,), width=int(1.6 * u))
    d.line([(rx, ry), (rx + raio * 0.45, ry + raio * 0.3)], fill=destaque + (255,), width=int(1.6 * u))
    d.text((x + 19 * u, ry + 4.5 * u), resto, font=fonte(12.5, False), fill=suave + (255,), anchor="ls")
    base.paste(cam, (0, 0), cam)
    return base


def main():
    pasta = glob.glob(os.path.join(RAIZ, "ferramentas", "testes_tela", ".tmp", "*", "gthud", "vetor"))
    if not pasta:
        print("sem arquivos de mapa de teste: rode um teste de tela antes")
        return

    def ler(z, x, y):
        for raiz in pasta:
            caminho = os.path.join(raiz, str(z), str(x), "%d.pbf" % y)
            if os.path.exists(caminho):
                with open(caminho, "rb") as f:
                    return f.read()
        return None
    # uma rota de verdade pelo centro (servidor de rotas)
    r = rotas.pedir_rota((-16.6730, -49.2590), (-16.6860, -49.2520))
    nav = Navegacao(r, lambda *a, **k: None)
    lat, lon, _ = r.ponto_em(330.0)
    nav.atualizar(lat, lon, 28.0, 1.0)
    ancora = (lat, lon)
    texto, inicio, aqui = segundo_plano.desenho_da_rota(nav, ancora)
    pontos = [tuple(map(float, p.split(","))) for p in texto.split(";")]
    ruas = mini_mapa.ruas_perto(ler, lat, lon, ancora)
    textos = ("60 m", "Vire à esquerda", "Rua do Ribeirão", "28", "4 min · 1,6 km · 12:47")
    a = painel(False, textos, pontos, inicio, aqui, ruas)
    b = painel(True, textos, pontos, inicio, aqui, ruas)
    c = painel(False, ("1,2 km", "Siga em frente", "Avenida Goiás", "41", "9 min · 3,8 km · 13:02"),
               pontos, inicio, aqui, ruas, alerta=2)
    junto = Image.new("RGB", (a.width, a.height * 3 + 40), (14, 17, 24))
    for k, im in enumerate((a, b, c)):
        junto.paste(im, (0, k * (a.height + 20)))
    saida = os.path.join(RAIZ, "ferramentas", "testes_tela", "fotos_painel")
    os.makedirs(saida, exist_ok=True)
    junto.save(os.path.join(saida, "painel_previa.png"))
    print("ok", junto.size, len(ruas), "ruas", len(pontos), "pontos da rota")


if __name__ == "__main__":
    main()
