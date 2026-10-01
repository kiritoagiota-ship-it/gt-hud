"""Gera os dados de Goiânia que vão DENTRO do APK (busca e avisos sem
internet, sem conta e sem custo):

  dados/goiania_lugares.db   ~70 mil lugares (comércios, serviços...) da
                             Overture Maps (licença CDLA Permissive 2.0;
                             crédito "Overture Maps Foundation" nos Ajustes)
  dados/goiania_sinais.json  semáforos e lombadas do OpenStreetMap (ODbL)

Roda no PC, num venv com o pacote "overturemaps" (fica fora do APK):
  python -m venv ovt
  ovt\\Scripts\\python -m pip install overturemaps
  ovt\\Scripts\\python ferramentas\\gerar_goiania.py

Refazer de tempos em tempos (lugares novos abrem, outros fecham).
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from goiania import LIMITES  # noqa: E402

DADOS = os.path.join(RAIZ, "dados")
CONFIANCA_MIN = 0.25   # abaixo disso a Overture tem muito lugar fechado/duplicado
OVERPASS = "https://overpass-api.de/api/interpreter"

# categoria da Overture -> palavras em português (para buscar "barbearia" e
# achar quem não tem a palavra no nome, e para mostrar no resultado)
CATEGORIAS = {
    "barber": "barbearia", "beauty_salon": "salão de beleza", "hair_salon": "cabeleireiro salão",
    "nail_salon": "manicure unhas", "spa": "spa estética", "tattoo_and_piercing": "tatuagem piercing",
    "restaurant": "restaurante", "brazilian_restaurant": "restaurante", "pizza_restaurant": "pizzaria",
    "burger_restaurant": "hamburgueria lanchonete", "fast_food_restaurant": "lanchonete fast food",
    "sandwich_shop": "lanchonete", "barbecue_restaurant": "churrascaria", "ice_cream_shop": "sorveteria",
    "dessert_shop": "doceria", "bakery": "padaria", "coffee_shop": "cafeteria café", "cafe": "café",
    "bar": "bar", "smoothie_juice_bar": "sucos", "butcher_shop": "açougue",
    "grocery_store": "mercado supermercado", "convenience_store": "conveniência",
    "warehouse_club_store": "atacadista", "liquor_store": "distribuidora bebidas",
    "pharmacy": "farmácia drogaria", "hospital": "hospital", "doctors_office": "consultório médico",
    "dental_clinic": "dentista odontologia", "general_dentistry": "dentista",
    "veterinarian": "veterinário", "pet_store": "pet shop", "animal_or_pet_service": "pet shop",
    "laboratory_testing": "laboratório exames", "physical_therapy": "fisioterapia",
    "gym": "academia", "pilates_studio": "pilates", "martial_arts_club": "luta artes marciais",
    "school": "escola", "private_school": "escola", "public_school": "escola", "preschool": "creche escola",
    "elementary_school": "escola", "college_university": "faculdade universidade",
    "language_school": "escola de idiomas", "driving_school": "autoescola",
    "christian_place_of_worship": "igreja", "pentecostal_place_of_worship": "igreja",
    "protestant_place_of_worship": "igreja", "roman_catholic_place_of_worship": "igreja católica",
    "baptist_place_of_worship": "igreja batista",
    "gas_station": "posto de gasolina combustível", "automotive_repair": "oficina mecânica",
    "auto_parts_store": "autopeças", "tire_dealer_and_repair": "borracharia pneus",
    "car_wash": "lava jato lavagem", "auto_detailing": "estética automotiva",
    "motorcycle_repair": "oficina de moto", "motorcycle_dealer": "concessionária de motos",
    "auto_dealer": "concessionária", "bike_store": "bicicletaria bike", "bank": "banco",
    "bank_or_credit_union": "banco", "shopping_mall": "shopping", "department_store": "loja de departamento",
    "clothing_store": "loja de roupas", "shoe_store": "sapataria calçados", "mobile_phone_store": "celulares",
    "hardware_store": "material de construção", "building_supply_store": "material de construção",
    "furniture_store": "móveis", "eyewear_store": "ótica", "jewelry_store": "joalheria",
    "hotel": "hotel", "lodging": "pousada hospedagem", "park": "parque", "police_station": "polícia delegacia",
    "government_office": "órgão público", "laundromat": "lavanderia", "printing_service": "gráfica",
    "accountant": "contador contabilidade", "attorney_or_law_firm": "advogado",
    "real_estate_service": "imobiliária", "real_estate_agent": "imobiliária corretor",
}


def normalizar(texto):
    """Sem acento, minúsculo: "Barbearia São José" -> "barbearia sao jose"."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(t.lower().split())


def baixar_lugares(pasta):
    """Lugares da Overture dentro de LIMITES (precisa do pacote overturemaps)."""
    lat0, lon0, lat1, lon1 = LIMITES
    saida = os.path.join(pasta, "lugares.parquet")
    exe = os.path.join(os.path.dirname(sys.executable), "overturemaps")
    subprocess.run([exe, "download", "--bbox=%s,%s,%s,%s" % (lon0, lat0, lon1, lat1),
                    "-f", "geoparquet", "--type=place", "-o", saida], check=True)
    import pyarrow.parquet as pq
    return pq.read_table(saida, columns=["names", "taxonomy", "addresses", "confidence",
                                         "geometry"]).to_pylist()


def ponto_wkb(wkb):
    """Ponto WKB (little-endian) -> (lat, lon)."""
    import struct
    lon, lat = struct.unpack("<dd", bytes(wkb)[5:21])
    return lat, lon


def gerar_lugares(linhas, caminho):
    if os.path.exists(caminho):
        os.remove(caminho)
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE lugares (nome TEXT, busca TEXT, categoria TEXT, endereco TEXT,"
                " lat REAL, lon REAL, conf REAL)")
    n = 0
    vistos = set()
    for r in linhas:
        nome = ((r.get("names") or {}).get("primary") or "").strip()
        conf = r.get("confidence") or 0.0
        if not nome or conf < CONFIANCA_MIN:
            continue
        lat, lon = ponto_wkb(r["geometry"])
        chave = (normalizar(nome), round(lat, 4), round(lon, 4))
        if chave in vistos:
            continue  # o mesmo lugar vindo de duas fontes
        vistos.add(chave)
        cat = CATEGORIAS.get((r.get("taxonomy") or {}).get("primary") or "", "")
        end = (r.get("addresses") or [{}])[0] or {}
        partes = [end.get("freeform") or "", end.get("locality") or ""]
        endereco = ", ".join(p.strip() for p in partes if p and p.strip() and "not-applicable" not in p)
        con.execute("INSERT INTO lugares VALUES (?,?,?,?,?,?,?)",
                    (nome, normalizar(nome + " " + cat), cat.split(" ")[0] if cat else "",
                     endereco[:120], round(lat, 6), round(lon, 6), round(conf, 3)))
        n += 1
    con.commit()
    con.execute("VACUUM")
    con.close()
    return n


def gerar_sinais(caminho):
    lat0, lon0, lat1, lon1 = LIMITES
    caixa = "(%s,%s,%s,%s)" % (lat0, lon0, lat1, lon1)
    consulta = ("[out:json][timeout:180];(node[\"highway\"=\"traffic_signals\"]%s;"
                "node[\"highway\"=\"crossing\"][\"crossing\"=\"traffic_signals\"]%s;"
                "node[\"traffic_calming\"]%s;);out body;" % (caixa, caixa, caixa))
    pedido = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": consulta}).encode(),
                                    headers={"User-Agent": "GT-HUD/1.0 (app pessoal de bike)"})
    try:
        import certifi
        import ssl
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = None
    dados = json.loads(urllib.request.urlopen(pedido, context=ctx, timeout=300).read())
    semaforos, lombadas = [], []
    for e in dados["elements"]:
        t = e.get("tags", {})
        ponto = [round(e["lat"], 6), round(e["lon"], 6)]
        if t.get("traffic_calming") in ("hump", "bump", "table", "cushion", "yes"):
            lombadas.append(ponto)
        elif t.get("highway") == "traffic_signals" or t.get("crossing") == "traffic_signals":
            semaforos.append(ponto)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"semaforos": semaforos, "lombadas": lombadas}, f, separators=(",", ":"))
    return len(semaforos), len(lombadas)


def main():
    os.makedirs(DADOS, exist_ok=True)
    with tempfile.TemporaryDirectory() as pasta:
        n = gerar_lugares(baixar_lugares(pasta), os.path.join(DADOS, "goiania_lugares.db"))
    print("lugares:", n)
    print("semaforos, lombadas:", gerar_sinais(os.path.join(DADOS, "goiania_sinais.json")))


if __name__ == "__main__":
    main()
