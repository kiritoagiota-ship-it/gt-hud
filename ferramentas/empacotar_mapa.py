"""Monta dados/goiania_mapa.db: o mapa de Goiânia INTEIRA que vai dentro do
APK (pedido do dono em 07/10/2026: arrastar e dar zoom sem esperar download).

    python ferramentas/empacotar_mapa.py

Baixa do OpenFreeMap todos os pedaços (tiles) dos zooms 11 a 14 que cobrem
goiania.LIMITES e guarda num arquivo só (SQLite; cada tile comprimido com
zlib). Rodar de novo de vez em quando para o mapa do app acompanhar as
mudanças do OpenStreetMap (ruas novas, mãos trocadas).
"""
import os
import sqlite3
import sys
import time
import zlib

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_FILELOG", "1")

import mapa_vetor  # noqa: E402
import rede  # noqa: E402

DESTINO = os.path.join(RAIZ, "dados", "goiania_mapa.db")


def main():
    try:
        url = rede.baixar_json(mapa_vetor.TILEJSON, timeout=20)["tiles"][0]
    except Exception as e:
        print("sem a versão atual dos tiles (%s): usando a conhecida" % e)
        url = mapa_vetor.URL_PADRAO
    lista = mapa_vetor.FonteVetorial.tiles_goiania()
    provisorio = DESTINO + ".novo"
    if os.path.exists(provisorio):
        os.remove(provisorio)
    con = sqlite3.connect(provisorio)
    con.execute("CREATE TABLE tiles (z INTEGER, x INTEGER, y INTEGER, dados BLOB, PRIMARY KEY (z, x, y))")
    con.execute("CREATE TABLE sobre (chave TEXT PRIMARY KEY, valor TEXT)")
    cru = comprimido = 0
    for n, (z, x, y) in enumerate(lista, 1):
        for tentativa in range(4):
            try:
                dados = rede.baixar(url.format(z=z, x=x, y=y), timeout=30)
                break
            except Exception as e:
                print("  de novo %d/%d/%d: %s" % (z, x, y, e))
                time.sleep(2 + 3 * tentativa)
        else:
            con.close()
            os.remove(provisorio)
            sys.exit("não consegui baixar %d/%d/%d: nada foi trocado" % (z, x, y))
        pequeno = zlib.compress(dados, 9)
        cru += len(dados)
        comprimido += len(pequeno)
        con.execute("INSERT INTO tiles VALUES (?,?,?,?)", (z, x, y, pequeno))
        if n % 25 == 0 or n == len(lista):
            print("%d de %d  (%.1f MB)" % (n, len(lista), comprimido / 1e6), flush=True)
    con.executemany("INSERT INTO sobre VALUES (?,?)",
                    [("url", url), ("feito_em", time.strftime("%Y-%m-%d")), ("tiles", str(len(lista)))])
    con.commit()
    con.execute("VACUUM")
    con.close()
    os.replace(provisorio, DESTINO)
    print("pronto: %s, %d tiles, %.1f MB (sem comprimir seriam %.1f MB)" % (
        DESTINO, len(lista), os.path.getsize(DESTINO) / 1e6, cru / 1e6))


if __name__ == "__main__":
    main()
