"""Firebase Realtime Database de MENTIRA, para testar o "corrida ao vivo"
no PC sem conta nenhuma (testes/test_ao_vivo.py e a página
docs/acompanhar/index.html).

Imita só o que o app e a página usam: GET, PUT e PATCH em caminhos
".../x.json", PATCH com chaves "a/b/c", orderBy="$key"&startAt=..., e as
mesmas regras que o dono cola no banco de verdade:
- só se escreve em corridas/<código> (código com 20+ letras), mandando a
  senha "s"; depois de criada, só com a MESMA senha; não dá para apagar;
- só se lê corridas/<código>/pub (e o que está dentro).

    python ferramentas/firebase_falso.py 8765
"""
import json
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _pegar(arvore, partes):
    for p in partes:
        if not isinstance(arvore, dict) or p not in arvore:
            return None
        arvore = arvore[p]
    return arvore


def _por(arvore, partes, valor):
    for p in partes[:-1]:
        if not isinstance(arvore.get(p), dict):
            arvore[p] = {}
        arvore = arvore[p]
    if valor is None:
        arvore.pop(partes[-1], None)
    else:
        arvore[partes[-1]] = valor


class Banco:
    def __init__(self):
        self.dados = {}
        self.trava = threading.Lock()
        self.escritas = []   # (método, caminho) de cada escrita aceita

    def ler(self, partes, consulta):
        if len(partes) < 3 or partes[0] != "corridas" or partes[2] != "pub":
            return 401, {"error": "Permission denied"}
        with self.trava:
            valor = json.loads(json.dumps(_pegar(self.dados, partes)))
        inicio = consulta.get("startAt", [None])[0]
        if isinstance(valor, dict) and consulta.get("orderBy", [""])[0] == '"$key"' and inicio:
            inicio = json.loads(inicio)
            valor = {k: v for k, v in valor.items() if k >= inicio}
        return 200, valor

    def escrever(self, metodo, partes, corpo):
        if len(partes) != 2 or partes[0] != "corridas" or len(partes[1]) < 20:
            return 401, {"error": "Permission denied"}
        with self.trava:
            atual = _pegar(self.dados, partes)
            novo = json.loads(json.dumps(atual)) if (metodo == "PATCH" and isinstance(atual, dict)) else {}
            if metodo == "PATCH":
                for chave, valor in (corpo or {}).items():
                    _por(novo, chave.split("/"), valor)
            else:
                novo = corpo
            senha_ok = isinstance(novo, dict) and isinstance(novo.get("s"), str) and (
                atual is None or atual.get("s") == novo.get("s"))
            if not senha_ok:
                return 401, {"error": "Permission denied"}
            _por(self.dados, partes, novo)
            self.escritas.append((metodo, "/".join(partes)))
        return 200, corpo


def servidor(porta=0, banco=None):
    """(servidor, banco, endereço). Já atendendo numa thread."""
    banco = banco or Banco()

    class Pedido(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _responder(self, codigo, valor):
            dados = json.dumps(valor).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def _caminho(self):
            url = urllib.parse.urlparse(self.path)
            caminho = url.path
            if not caminho.endswith(".json"):
                return None, {}
            return [p for p in caminho[:-5].split("/") if p], urllib.parse.parse_qs(url.query)

        def do_GET(self):
            partes, consulta = self._caminho()
            if partes is None:
                return self._responder(404, {"error": "use .json"})
            self._responder(*banco.ler(partes, consulta))

        def _escrita(self, metodo):
            partes, _ = self._caminho()
            corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"null")
            if partes is None:
                return self._responder(404, {"error": "use .json"})
            self._responder(*banco.escrever(metodo, partes, corpo))

        def do_PUT(self):
            self._escrita("PUT")

        def do_PATCH(self):
            self._escrita("PATCH")

    http = ThreadingHTTPServer(("127.0.0.1", porta), Pedido)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    return http, banco, "http://127.0.0.1:%d" % http.server_address[1]


if __name__ == "__main__":
    http, _, endereco = servidor(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
    print("Firebase de mentira em", endereco, "(Ctrl+C para parar)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        http.shutdown()
