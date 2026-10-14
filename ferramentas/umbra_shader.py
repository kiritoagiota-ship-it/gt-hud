"""Leva o desenho do rosto do Umbra da página de prévia para o app.

O rosto é desenhado pela placa de vídeo (um "fragment shader" GLSL) e é criado e ajustado
na página ferramentas/umbra_previa.html (abre no navegador, com botões de estado e de
comparação). Esta ferramenta copia o desenho de lá (o bloco <script id="pintor">) para
widgets/umbra_pintor.py, que é o que o app usa.

Rodar da raiz do projeto, depois de mexer no desenho da página:
    python ferramentas/umbra_shader.py
"""
import io
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGINA = os.path.join(RAIZ, "ferramentas", "umbra_previa.html")
SAIDA = os.path.join(RAIZ, "widgets", "umbra_pintor.py")


def shader_da_pagina(html):
    fonte = re.search(r'<script id="pintor" type="x-shader/x-fragment">(.*?)</script>', html, re.S).group(1).strip()
    # no PC (OpenGL de mesa) a linha de "precision" não é aceita; no celular (OpenGL ES) ela vale
    velho = "#ifdef GL_FRAGMENT_PRECISION_HIGH\nprecision highp float;\n#else\nprecision mediump float;\n#endif"
    novo = "#ifdef GL_ES\n" + velho + "\n#endif"
    assert fonte.count(velho) == 1, "o começo do desenho mudou: confira a linha de precision"
    return fonte.replace(velho, novo) + "\n"


def main():
    html = io.open(PAGINA, encoding="utf-8").read().replace("\r\n", "\n")
    fonte = shader_da_pagina(html)
    assert "'''" not in fonte and "\\" not in fonte
    texto = ('"""O desenho do rosto do Umbra (fragment shader GLSL ES 1.0).\n\n'
             'GERADO por ferramentas/umbra_shader.py a partir de ferramentas/umbra_previa.html: não edite aqui,\n'
             'edite a página (e confira no navegador) e rode a ferramenta de novo.\n"""\n'
             "FONTE = r'''" + fonte + "'''\n")
    with io.open(SAIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    print("desenho do Umbra copiado: %d linhas -> %s" % (fonte.count("\n"), os.path.relpath(SAIDA, RAIZ)))


if __name__ == "__main__":
    main()
