"""Monta dados/mapa_pronto.db: os pedaços do mapa JÁ DESENHADOS (geometria
pronta para a placa de vídeo) dos zooms mais usados, da cidade inteira.

    python ferramentas/empacotar_prontos.py

O build do APK roda isto sozinho (.github/workflows/build.yml), sempre com o
código de desenho daquele build; o arquivo (~150 MB) não vai para o git.
Sem ele o app funciona igual, só desenha cada pedaço na primeira vez que
ele aparece (e guarda no celular).
"""
import marshal
import os
import sqlite3
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_FILELOG", "1")
os.environ.setdefault("KIVY_LOG_MODE", "PYTHON")

import mapa_vetor  # noqa: E402
import mvt  # noqa: E402

CAMADAS = ("landuse", "park", "landcover", "water", "building",
           "transportation", "transportation_name", "place", "poi")


def main(zooms=mapa_vetor.ZOOMS_PRONTOS):
    if not mapa_vetor.partes_no_pacote():
        sys.exit("falta dados/goiania_mapa.db (rode ferramentas/empacotar_mapa.py)")
    origem = mapa_vetor.origem_padrao()
    d = mapa_vetor.DENSIDADE_PRONTOS
    provisorio = mapa_vetor.PRONTOS + ".novo"
    if os.path.exists(provisorio):
        os.remove(provisorio)
    con = sqlite3.connect(provisorio)
    con.execute("CREATE TABLE prontos (rz INTEGER, dz INTEGER, tx INTEGER, ty INTEGER, dados BLOB, "
                "PRIMARY KEY (rz, dz, tx, ty))")
    con.execute("CREATE TABLE sobre (chave TEXT PRIMARY KEY, valor TEXT)")
    t0 = time.time()
    total = 0
    for rz in zooms:
        dz = mapa_vetor.z_dados(rz)
        n = tamanho = 0
        for z, x, y in mapa_vetor.FonteVetorial.tiles_goiania((dz,)):
            camadas = mvt.ler(mapa_vetor.do_pacote(z, x, y), CAMADAS)
            pronto = mapa_vetor.preparar(camadas, dz, x, y, rz, origem, d, d)
            if not pronto.get("ok"):
                continue   # este o celular desenha (e tenta de novo) por conta própria
            dados = mapa_vetor.empacotar(pronto)
            con.execute("INSERT INTO prontos VALUES (?,?,?,?,?)", (rz, dz, x, y, dados))
            n += 1
            tamanho += len(dados)
        con.commit()
        total += tamanho
        print("zoom %d: %d pedaços, %.1f MB (%.0f s)" % (rz, n, tamanho / 1e6, time.time() - t0), flush=True)
    con.executemany("INSERT INTO sobre VALUES (?,?)", [
        ("versao", str(mapa_vetor.VERSAO_PREPARO)), ("mapa", mapa_vetor.data_do_pacote()),
        ("marshal", str(mapa_vetor.FORMATO_MARSHAL)), ("densidade", str(d)), ("zooms", ",".join(map(str, zooms)))])
    con.commit()
    con.close()
    os.replace(provisorio, mapa_vetor.PRONTOS)
    print("pronto: %s, %.0f MB" % (mapa_vetor.PRONTOS, total / 1e6))


if __name__ == "__main__":
    main()
