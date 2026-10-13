"""Gera os ícones do app a partir da LOGO (icone/logo.png), a imagem que o dono escolheu
em 14/10/2026 ("é a nossa logo agora"). Substitui o desenho feito por gerar_icones.py.

Rodar da raiz do projeto:  python ferramentas/icones_da_logo.py
Grava em icone/:
  icon.png       512x512  ícone clássico (cantos arredondados, fora deles transparente)
  icone_fg.png   432x432  ícone adaptativo, frente: a logo um pouco menor, para o rosto, o
                          pino e o balão caberem na parte que o Android mostra (o miolo:
                          cada celular recorta de um jeito, redondo ou quadrado de cantos)
  icone_bg.png   432x432  ícone adaptativo, fundo: a cor escura da borda da logo
  presplash.png  900x900  imagem da abertura, sumindo nas beiradas para a cor de
                          android.presplash_color do buildozer.spec
  gt-hud.ico              ícone da pasta do projeto no Windows
"""
import os

from PIL import Image, ImageDraw, ImageFilter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA = os.path.join(RAIZ, "icone")
FUNDO_DA_LOGO = (6, 6, 13)        # a cor das beiradas da imagem
COR_DA_ABERTURA = (4, 7, 11)      # android.presplash_color = #04070B
MIOLO = 0.76                      # quanto da frente do ícone adaptativo a logo ocupa


def _recorte_arredondado(tam, folga, raio):
    """Máscara (L) de um quadrado de cantos redondos, desenhada 4x maior para a borda sair lisa."""
    g = 4
    m = Image.new("L", (tam * g, tam * g), 0)
    ImageDraw.Draw(m).rounded_rectangle([folga * g, folga * g, (tam - folga) * g - 1, (tam - folga) * g - 1],
                                        radius=raio * g, fill=255)
    return m.resize((tam, tam), Image.LANCZOS)


def main():
    logo = Image.open(os.path.join(PASTA, "logo.png")).convert("RGB")

    # ícone clássico: a logo inteira, com o lado de fora da moldura transparente
    classico = logo.resize((512, 512), Image.LANCZOS).convert("RGBA")
    classico.putalpha(_recorte_arredondado(512, 26, 112))
    classico.save(os.path.join(PASTA, "icon.png"))

    # ícone adaptativo
    frente = Image.new("RGB", (432, 432), FUNDO_DA_LOGO)
    lado = int(round(432 * MIOLO))
    frente.paste(logo.resize((lado, lado), Image.LANCZOS), ((432 - lado) // 2, (432 - lado) // 2))
    frente.convert("RGBA").save(os.path.join(PASTA, "icone_fg.png"))
    Image.new("RGBA", (432, 432), FUNDO_DA_LOGO + (255,)).save(os.path.join(PASTA, "icone_bg.png"))

    # abertura: a logo no meio, apagando-se nas beiradas até a cor do resto da tela
    abertura = Image.new("RGB", (900, 900), COR_DA_ABERTURA)
    lado = 820
    arte = logo.resize((lado, lado), Image.LANCZOS)
    some = _recorte_arredondado(lado, 70, 150).filter(ImageFilter.GaussianBlur(34))
    abertura.paste(arte, ((900 - lado) // 2, (900 - lado) // 2), some)
    abertura.save(os.path.join(PASTA, "presplash.png"))

    # ícone da pasta no Windows
    classico.resize((256, 256), Image.LANCZOS).save(os.path.join(PASTA, "gt-hud.ico"),
                                                    sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("icones gerados em", PASTA)


if __name__ == "__main__":
    main()
