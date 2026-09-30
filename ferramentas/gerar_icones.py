"""Gera o ícone e a tela de abertura do GT-HUD (fica fora do APK).

Rodar da raiz do projeto:  python ferramentas/gerar_icones.py
Grava em icone/:
  icon.png       512x512  ícone comum (celulares antigos / lojas)
  icone_fg.png   432x432  ícone adaptativo, frente (logo, fundo transparente)
  icone_bg.png   432x432  ícone adaptativo, fundo
  presplash.png  900x900  imagem da abertura (o resto da tela é a cor
                          android.presplash_color do buildozer.spec)

O desenho repete o velocímetro do app: anel de 270 graus em segmentos,
acesos em ciano até o limite e laranja depois dele, e "GT" no meio.
Tudo é desenhado 4x maior e reduzido no fim, para as bordas saírem lisas.
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(RAIZ, "icone")
SS = 4  # superamostragem

# mesmas cores de tema.py
FUNDO = (4, 7, 11)
PAINEL = (10, 21, 32)
CIANO = (0, 229, 255)
CIANO_APAGADO = (13, 52, 64)
LARANJA = (255, 138, 0)
BRANCO = (242, 251, 255)

SEGMENTOS = 18
ACESOS = 15        # quantos segmentos acesos
LIMITE = 12        # a partir deste, laranja (como acima do limite no app)


def _fonte():
    # acha a fonte do Kivy sem importar o Kivy (importar abre log em ~/.kivy)
    from importlib.util import find_spec
    pasta = os.path.dirname(find_spec("kivy").origin)
    return os.path.join(pasta, "data", "fonts", "Roboto-Bold.ttf")


def _angulo_pil(a_kivy):
    # no app 0 grau é o topo, sentido horário; no Pillow 0 grau é a direita
    return a_kivy - 90.0


def logo(tam, texto=True):
    """Anel segmentado + "GT", centralizado num quadrado transparente."""
    t = tam * SS
    img = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    cx = cy = t / 2.0
    r = t * 0.40              # raio do meio do anel
    esp = t * 0.085           # espessura do anel
    passo = 270.0 / SEGMENTOS
    folga = passo * 0.22

    def arco(d, i, cor, largura, raio=r):
        a0 = -135.0 + i * passo + folga / 2.0
        a1 = a0 + passo - folga
        caixa = [cx - raio, cy - raio, cx + raio, cy + raio]
        d.arc(caixa, _angulo_pil(a0), _angulo_pil(a1), fill=cor, width=int(largura))

    # brilho: os segmentos acesos, largos e desfocados por baixo
    brilho = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    db = ImageDraw.Draw(brilho)
    for i in range(ACESOS):
        cor = LARANJA if i >= LIMITE else CIANO
        arco(db, i, cor + (150,), esp * 1.6)
    brilho = brilho.filter(ImageFilter.GaussianBlur(t * 0.03))
    img.alpha_composite(brilho)

    d = ImageDraw.Draw(img)
    for i in range(SEGMENTOS):
        if i < ACESOS:
            cor = (LARANJA if i >= LIMITE else CIANO) + (255,)
        else:
            cor = CIANO_APAGADO + (255,)
        arco(d, i, cor, esp)

    # anel fino por dentro e a marca do limite por fora (iguais ao app)
    ri = r - esp * 1.15
    d.arc([cx - ri, cy - ri, cx + ri, cy + ri], _angulo_pil(-135), _angulo_pil(135),
          fill=CIANO + (70,), width=max(1, int(t * 0.008)))
    import math
    a = math.radians(-135.0 + LIMITE * passo)
    p1 = (cx + math.sin(a) * (r + esp * 0.7), cy - math.cos(a) * (r + esp * 0.7))
    p2 = (cx + math.sin(a) * (r + esp * 1.35), cy - math.cos(a) * (r + esp * 1.35))
    d.line([p1, p2], fill=LARANJA + (255,), width=int(t * 0.018))

    if texto:
        fonte = ImageFont.truetype(_fonte(), int(t * 0.30))
        d.text((cx, cy + t * 0.02), "GT", font=fonte, fill=BRANCO + (255,), anchor="mm")

    return img.resize((tam, tam), Image.LANCZOS)


def fundo_radial(tam, cantos=0.0):
    """Quadrado escuro com um leve brilho azulado no centro."""
    grad = Image.radial_gradient("L").resize((tam, tam), Image.BICUBIC)  # 0 no centro
    claro = Image.new("RGBA", (tam, tam), PAINEL + (255,))
    escuro = Image.new("RGBA", (tam, tam), FUNDO + (255,))
    img = Image.composite(escuro, claro, grad)
    if cantos:
        mascara = Image.new("L", (tam * SS, tam * SS), 0)
        ImageDraw.Draw(mascara).rounded_rectangle(
            [0, 0, tam * SS - 1, tam * SS - 1], radius=int(tam * SS * cantos), fill=255)
        img.putalpha(mascara.resize((tam, tam), Image.LANCZOS))
    return img


def colar_centro(base, img, fracao):
    lado = int(base.width * fracao)
    peq = img.resize((lado, lado), Image.LANCZOS)
    base.alpha_composite(peq, ((base.width - lado) // 2, (base.height - lado) // 2))
    return base


def main():
    os.makedirs(SAIDA, exist_ok=True)
    grande = logo(1024)

    # ícone comum: quadrado de cantos redondos com o logo
    icone = colar_centro(fundo_radial(512, cantos=0.22), grande, 0.86)
    icone.save(os.path.join(SAIDA, "icon.png"))

    # adaptativo: o Android corta a borda (círculo, gota...), então o logo
    # fica dentro da zona segura (66 de 108 dp = ~61% do quadrado)
    fg = colar_centro(Image.new("RGBA", (432, 432), (0, 0, 0, 0)), grande, 0.60)
    fg.save(os.path.join(SAIDA, "icone_fg.png"))
    fundo_radial(432).save(os.path.join(SAIDA, "icone_bg.png"))

    # abertura: logo + nome, sobre a mesma cor do fundo do app
    abertura = Image.new("RGBA", (900, 900), FUNDO + (255,))
    colar_centro(abertura, grande, 0.46)
    d = ImageDraw.Draw(abertura)
    d.text((450, 690), "GT-HUD", font=ImageFont.truetype(_fonte(), 64),
           fill=CIANO + (255,), anchor="mm")
    abertura.convert("RGB").save(os.path.join(SAIDA, "presplash.png"))
    print("ok:", ", ".join(sorted(os.listdir(SAIDA))))


if __name__ == "__main__":
    main()
