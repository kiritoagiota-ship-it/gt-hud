"""Prévia no PC do cartão da notificação (o de verdade é Java e só roda no Android:
java/org/kirito/gthud/CartaoNotificacao.java). Mesmas medidas e cores; serve para
ver o desenho antes de gerar o APK.

    python ferramentas/previa_notificacao.py   ->  ferramentas/previa_notificacao.png
"""
import os

from PIL import Image, ImageDraw, ImageFont

U = 2.5              # pixels por "dp" do desenho
LARGURA_DP = 328     # celular de 360 dp de largura, menos as margens da notificação
CORES = {   # (claro, escuro, monarca)
    "fundo_cima": ("#FFFFFF", "#0C1826", "#17133F"), "fundo_baixo": ("#EAF1F5", "#05090F", "#07061A"),
    "borda": ("#00788F", "#19E3FF", "#5AA0FF"), "aura": ("#00788F", "#19E3FF", "#9B5CFF"),
    "forte": ("#0A1A24", "#F2FBFF", "#EEF0FF"), "suave": ("#3F6272", "#A9DCEA", "#A7A2F0"),
    "apagado": ("#C9D8DE", "#0F2A36", "#231F58"),
}
TEMAS = ("claro", "escuro", "monarca")


def _rgb(hexa):
    return tuple(int(hexa[i:i + 2], 16) for i in (1, 3, 5))


def _fonte(tamanho, negrito=True):
    for nome in (("arialbd.ttf", "segoeuib.ttf") if negrito else ("arial.ttf", "segoeui.ttf")):
        try:
            return ImageFont.truetype(nome, int(round(tamanho)))
        except OSError:
            pass
    return ImageFont.load_default()


def _misturar(a, b, f):
    return tuple(int(round(x + (y - x) * f)) for x, y in zip(a, b))


SETAS = {   # (pontos do caminho em frações do quadrado, para onde a ponta aponta): como no Java
    "direita": ([(0.28, 0.92), (0.28, 0.36), (0.76, 0.36)], (1, 0)),
    "levemente_direita": ([(0.36, 0.92), (0.36, 0.52), (0.68, 0.20)], (0.707, -0.707)),
    "em_frente": ([(0.5, 0.92), (0.5, 0.24)], (0, -1)),
}


def seta(img, x0, y0, tam, acao, cor, aura):
    espelho = acao.endswith("esquerda")
    pts, (dx, dy) = SETAS.get(acao.replace("esquerda", "direita"), SETAS["em_frente"])
    if espelho:
        pts, dx = [(1 - x, y) for x, y in pts], -dx
    caminho = [(x0 + x * tam, y0 + y * tam) for x, y in pts]
    halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(halo).line(caminho, fill=aura + (0x50,), width=int(tam * 0.22), joint="curve")
    img.alpha_composite(halo)
    d = ImageDraw.Draw(img)
    d.line(caminho, fill=cor + (255,), width=int(tam * 0.12), joint="curve")
    for px, py in caminho[:1]:
        r = tam * 0.06
        d.ellipse([px - r, py - r, px + r, py + r], fill=cor + (255,))
    tx, ty = caminho[-1]
    comp, meia = tam * 0.22, tam * 0.17
    d.polygon([(tx + dx * comp, ty + dy * comp), (tx - dy * meia, ty + dx * meia), (tx + dy * meia, ty - dx * meia)],
              fill=cor + (255,))


def cartao(tema, grande, rotulo, valor, lado, sub, segmentos, acesos, acao=""):
    cor = {nome: _rgb(v[TEMAS.index(tema)]) for nome, v in CORES.items()}
    u = U
    w, h = int(round(LARGURA_DP * u)), int(round((124 if grande else 46) * u))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    m, canto = 3 * u, (13 if grande else 9) * u
    contorno = [(m + canto, m), (w - m, m), (w - m, h - m - canto), (w - m - canto, h - m), (m, h - m), (m, m + canto)]
    # fundo em degradê (recortado pelo contorno)
    degrade = Image.new("RGBA", (w, h))
    dd = ImageDraw.Draw(degrade)
    for y in range(h):
        f = min(1.0, max(0.0, (y - m) / max(1.0, h - 2 * m)))
        dd.line([(0, y), (w, y)], fill=_misturar(cor["fundo_cima"], cor["fundo_baixo"], f) + (255,))
    mascara = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mascara).polygon(contorno, fill=255)
    img.paste(degrade, (0, 0), mascara)
    linhas = Image.new("RGBA", (w, h), (0, 0, 0, 0))     # linhas finas de painel no fundo
    dl_ = ImageDraw.Draw(linhas)
    yy = m + 5 * u
    while yy < h - m:
        dl_.line([(m, yy), (w - m, yy)], fill=cor["borda"] + (0x10 if tema == "claro" else 0x17,), width=1)
        yy += 5 * u
    linhas.putalpha(Image.composite(linhas.getchannel("A"), Image.new("L", (w, h), 0), mascara))
    img = Image.alpha_composite(img, linhas)
    brilho = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(brilho).line(contorno + contorno[:1], fill=cor["aura"] + (0x22 if tema == "claro" else 0x48,),
                                width=int(5 * u), joint="curve")
    img = Image.alpha_composite(img, brilho)
    d = ImageDraw.Draw(img)
    d.line(contorno + contorno[:1], fill=cor["borda"] + (255,), width=max(1, int(1.3 * u)))
    e = canto * 0.9
    for traco in ([(m, m + canto + e), (m, m + canto), (m + canto, m), (m + canto + e, m)],
                  [(w - m, h - m - canto - e), (w - m, h - m - canto), (w - m - canto, h - m), (w - m - canto - e, h - m)]):
        d.line(traco, fill=cor["borda"] + (255,), width=int(2.8 * u))
    margem = 15 * u

    def barrinhas(x, y, cada, alto, vao, inclina):
        for n in range(segmentos):
            x0 = x + n * (cada + vao)
            forma = [(x0 + inclina, y), (x0 + cada + inclina, y), (x0 + cada, y + alto), (x0, y + alto)]
            if n < acesos:
                dela = _misturar(cor["borda"], cor["aura"], n / (segmentos - 1.0) if segmentos > 1 else 0.0)
                if n == acesos - 1:      # a barrinha da vez: mais clara
                    dela = _misturar(dela, (255, 255, 255), 0.42)
                halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                ImageDraw.Draw(halo).line(forma + forma[:1], fill=dela + (0x55,), width=int(3.2 * u), joint="curve")
                img.alpha_composite(halo)
                d.polygon(forma, fill=dela + (255,))
            else:
                d.polygon(forma, fill=cor["apagado"] + (255,))

    if not grande:
        x = margem
        if acao:
            tam = h - 2 * m - 12 * u
            seta(img, x, (h - tam) / 2.0, tam, acao, cor["borda"], cor["aura"])
            d = ImageDraw.Draw(img)
            x += tam + 8 * u
        elif segmentos > 0:
            alto, vao = h - 2 * m - 16 * u, 3.5 * u
            cada = min(12 * u, (w * 0.34) / segmentos - vao)
            barrinhas(x, (h - alto) / 2.0, cada, alto, vao, 4 * u)
            x += segmentos * (cada + vao) + 9 * u
        linha = h / 2.0
        f_lado, f_valor, f_rot = _fonte(16 * u), _fonte(19 * u), _fonte(11 * u, False)
        larg_lado = d.textlength(lado, font=f_lado) if lado else 0
        if lado:
            d.text((w - margem - larg_lado, linha + 5.8 * u), lado, font=f_lado, fill=cor["borda"], anchor="ls")
        d.text((x, linha + 6.8 * u), valor, font=f_valor, fill=cor["forte"], anchor="ls")
        x += d.textlength(valor, font=f_valor) + 8 * u
        if rotulo and x < w - margem - larg_lado - 40 * u:
            curto = rotulo.split("·")[-1].strip().lower()   # (na faixa cabe pouco: só o fim do rótulo)
            cabe = w - margem - larg_lado - 10 * u - x
            while curto and d.textlength(curto, font=f_rot) > cabe:
                curto = curto[:-2].rstrip() + "…" if len(curto) > 2 else ""
            d.text((x, linha + 5 * u), curto, font=f_rot, fill=cor["suave"], anchor="ls")
        return img

    dl, cy = 3.6 * u, 21 * u
    d.polygon([(margem + dl, cy - dl), (margem + 2 * dl, cy), (margem + dl, cy + dl), (margem, cy)], fill=cor["aura"])
    f_lado = _fonte(15 * u)
    if lado:
        d.text((w - margem - d.textlength(lado, font=f_lado), cy + 5.2 * u), lado, font=f_lado, fill=cor["borda"], anchor="ls")
    d.text((margem + 2 * dl + 7 * u, cy + 3.7 * u), rotulo,
           font=_fonte(10.5 * u), fill=cor["suave"], anchor="ls")
    x_valor = margem
    if acao:
        seta(img, margem, 28 * u, 40 * u, acao, cor["borda"], cor["aura"])
        d = ImageDraw.Draw(img)
        x_valor += 50 * u
    from PIL import ImageFilter
    brilho_n = Image.new("RGBA", (w, h), (0, 0, 0, 0))      # o brilho atrás do número
    ImageDraw.Draw(brilho_n).text((x_valor, 63 * u), valor, font=_fonte(33 * u), fill=cor["aura"] + (200,), anchor="ls")
    img.alpha_composite(brilho_n.filter(ImageFilter.GaussianBlur(4 * u)))
    d = ImageDraw.Draw(img)
    d.text((x_valor, 63 * u), valor, font=_fonte(33 * u), fill=cor["forte"], anchor="ls")
    if segmentos > 0:
        vao, inclina = 4 * u, 5 * u
        barrinhas(margem, 75 * u, (w - 2 * margem - inclina - (segmentos - 1) * vao) / segmentos, 15 * u, vao, inclina)
    if sub:
        d.text((margem, h - m - 9 * u), sub, font=_fonte(11.5 * u, False), fill=cor["suave"], anchor="ls")
    return img


def folha():
    """Os dois tamanhos, na bateria e na rota, nos três temas, numa imagem só."""
    exemplos = [("SISTEMA  ·  BATERIA DA MOTO", "12,4 km", "4/5", "Carga inteira pelo seu uso: uns 41 km", 5, 4),
                ("SISTEMA  ·  MISSÃO  ·  BARBEARIA IMAGEM", "200 m", "14 min",
                 "Vire à direita (Rua 9)  ·  faltam 2,3 km  ·  chega às 13:14", 12, 5, "direita")]
    pecas = []
    for tema in ("monarca", "escuro"):
        for ex in exemplos:
            ex = (ex[0] if tema == "monarca" else ex[0].replace("SISTEMA  ·  ", "").replace("MISSÃO", "ROTA"),) + ex[1:]
            pecas.append((tema, cartao(tema, False, *ex)))
            pecas.append((tema, cartao(tema, True, *ex)))
    w = max(p.width for _, p in pecas) + 60
    h = sum(p.height + 26 for _, p in pecas) + 30
    base = Image.new("RGB", (w, h), (18, 18, 22))
    y = 26
    for tema, p in pecas:
        fundo = (236, 238, 242) if tema == "claro" else (30, 30, 36)   # a cor da gaveta de notificações
        ImageDraw.Draw(base).rectangle([14, y - 10, w - 14, y + p.height + 10], fill=fundo)
        base.paste(p, (30, y), p)
        y += p.height + 26
    return base


if __name__ == "__main__":
    destino = os.path.join(os.path.dirname(os.path.abspath(__file__)), "previa_notificacao.png")
    folha().save(destino)
    print("salvo:", destino)
