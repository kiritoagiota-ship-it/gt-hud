"""Roda os testes de TELA do GT-HUD (janela no 2º monitor, x=2400; fotos em
ferramentas/testes_tela/fotos*). Precisa de vídeo: não roda no GitHub.

    python ferramentas/testes_tela/rodar_todos.py            (todos)
    python ferramentas/testes_tela/rodar_todos.py tela_novidades.py

Cada teste usa APPDATA/KIVY_HOME próprios (pasta .tmp aqui), sem mexer nos
dados do app de verdade, e escreve [CHECA] OK/FALHOU e [FIM] no fim.
Alguns usam a internet (rotas do Valhalla, busca de ruas, tiles do mapa).
"""
import os
import subprocess
import sys

PASTA = os.path.dirname(os.path.abspath(__file__))
TESTES = ["tela_navegacao.py", "tela_busca_recalculo.py", "tela_volta_do_fundo.py", "tela_chip_gps.py",
          "tela_velocimetro.py", "tela_novidades.py", "tela_fundo.py",
          "tela_apagar.py", "tela_zoom.py", "tela_colar.py", "tela_ao_vivo.py", "tela_tema.py", "tela_busca_nova.py", "tela_fim_renomear.py", "tela_polimento.py", "tela_rota_calma.py", "tela_informacoes.py", "tela_previa_animada.py", "tela_transito_mapa.py", "tela_mapa_pronto.py", "tela_icones.py", "tela_tomtom.py", "tela_noturna.py", "tela_abrir_com.py", "tela_aproximada.py", "tela_sinalizacao.py", "tela_polimento2.py", "tela_bateria.py"]


def rodar(nome):
    tmp = os.path.join(PASTA, ".tmp")
    env = dict(os.environ, APPDATA=os.path.join(tmp, "appdata"), KIVY_HOME=os.path.join(tmp, "kivyhome"),
               PYTHONIOENCODING="utf-8")
    os.makedirs(env["APPDATA"], exist_ok=True)
    saida = subprocess.run([sys.executable, os.path.join(PASTA, nome)], env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=600).stdout
    checas = [l for l in saida.splitlines() if l.startswith("[CHECA]")]
    falhas = [l for l in checas if "FALHOU" in l]
    print("%-28s %2d checagens, %d falhas" % (nome, len(checas), len(falhas)))
    for l in falhas:
        print("    " + l)
    return not falhas and any(l.startswith("[FIM]") for l in saida.splitlines())


if __name__ == "__main__":
    escolhidos = sys.argv[1:] or TESTES
    ok = all([rodar(n) for n in escolhidos])
    print("TUDO OK" if ok else "HOUVE FALHAS")
    sys.exit(0 if ok else 1)
