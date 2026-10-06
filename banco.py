"""Persistência das viagens em SQLite."""
import os
import sqlite3

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS viagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio REAL, fim REAL,
    distancia_m REAL, duracao_s REAL, tempo_mov_s REAL,
    vel_max_kmh REAL, vel_media_kmh REAL
);
CREATE TABLE IF NOT EXISTS pontos (
    viagem_id INTEGER, lat REAL, lon REAL, vel_kmh REAL, t REAL
);
CREATE INDEX IF NOT EXISTS idx_pontos_viagem ON pontos(viagem_id);
"""

_CAMPOS = ("id", "inicio", "fim", "distancia_m", "duracao_s",
           "tempo_mov_s", "vel_max_kmh", "vel_media_kmh", "destino")


class Banco:
    def __init__(self, pasta):
        os.makedirs(pasta, exist_ok=True)
        self.caminho = os.path.join(pasta, "gthud.db")
        with self._conectar() as c:
            c.executescript(_ESQUEMA)
            # banco de versões antigas: ganha a coluna do destino (toda viagem agora é uma rota)
            colunas = [l[1] for l in c.execute("PRAGMA table_info(viagens)")]
            if "destino" not in colunas:
                c.execute("ALTER TABLE viagens ADD COLUMN destino TEXT")

    def _conectar(self):
        return sqlite3.connect(self.caminho)

    def salvar_viagem(self, resumo, pontos):
        with self._conectar() as c:
            cur = c.execute(
                "INSERT INTO viagens (inicio, fim, distancia_m, duracao_s, tempo_mov_s,"
                " vel_max_kmh, vel_media_kmh, destino) VALUES (?,?,?,?,?,?,?,?)",
                (resumo["inicio"], resumo["fim"], resumo["distancia_m"],
                 resumo["duracao_s"], resumo["tempo_mov_s"],
                 resumo["vel_max_kmh"], resumo["vel_media_kmh"], resumo.get("destino") or ""))
            vid = cur.lastrowid
            c.executemany(
                "INSERT INTO pontos (viagem_id, lat, lon, vel_kmh, t) VALUES (?,?,?,?,?)",
                [(vid, *p) for p in pontos])
        return vid

    def listar_viagens(self):
        with self._conectar() as c:
            linhas = c.execute(
                "SELECT %s FROM viagens ORDER BY inicio DESC" % ",".join(_CAMPOS)).fetchall()
        return [dict(zip(_CAMPOS, l)) for l in linhas]

    def obter_viagem(self, vid):
        with self._conectar() as c:
            l = c.execute("SELECT %s FROM viagens WHERE id=?" % ",".join(_CAMPOS),
                          (vid,)).fetchone()
            if not l:
                return None, []
            pts = c.execute("SELECT lat, lon, vel_kmh, t FROM pontos WHERE viagem_id=?"
                            " ORDER BY t", (vid,)).fetchall()
        return dict(zip(_CAMPOS, l)), pts

    def apagar_viagem(self, vid):
        with self._conectar() as c:
            c.execute("DELETE FROM pontos WHERE viagem_id=?", (vid,))
            c.execute("DELETE FROM viagens WHERE id=?", (vid,))
