"""GPS real do Android, ouvindo só o satélite.

Quem recebe as posições é java/org/kirito/gthud/Localizacao.java; aqui o
Python só confere, algumas vezes por segundo, se chegou posição nova.

Histórico, para não repetir:
- O plyer.gps assina TODOS os provedores (gps, network, passive...). O de
  rede (wi-fi/antena) chega sem velocidade (vira 0 km/h) e com a posição
  pulando: só o provedor "gps" serve para velocímetro.
- Um ouvinte feito em Python (pyjnius, como o do plyer) não recebe NADA no
  Android 12+: o sistema entrega pelo onLocationChanged(List), método
  "default" da interface, que o Proxy do pyjnius não executa. No celular
  ficava "Buscando GPS" com 63 satélites vistos no céu aberto.

Só é importado no Android (jnius não existe no PC).
"""
from jnius import autoclass
from kivy.clock import Clock

PythonActivity = autoclass("org.kivy.android.PythonActivity")

PROVEDOR = "gps"
CONFERIR_S = 0.1  # o GPS manda 1 posição/s; conferir 10x/s atrasa no máximo 0,1 s


def _classe_satelites():
    """java/org/kirito/gthud/Satelites.java (conta satélites); None se faltar."""
    try:
        return autoclass("org.kirito.gthud.Satelites")
    except Exception as e:
        print("[gps] sem contador de satelites:", e)
        return None


def _classe_aproximada():
    """java/.../LocalizacaoAprox.java (posição por rede e última conhecida); None se faltar."""
    try:
        return autoclass("org.kirito.gthud.LocalizacaoAprox")
    except Exception as e:
        print("[gps] sem posicao aproximada:", e)
        return None


class GPSAndroid:
    def __init__(self, ao_receber, ao_status, ao_aproximada=None):
        self._atividade = PythonActivity.mActivity
        self._loc = autoclass("org.kirito.gthud.Localizacao")
        self._sat = _classe_satelites()
        # posição aproximada na hora (rede/última conhecida), enquanto o satélite não chega
        self._aprox = _classe_aproximada() if ao_aproximada is not None else None
        self._ao_aproximada = ao_aproximada
        self._aprox_visto = 0
        self._ao_receber = ao_receber
        self._ao_status = ao_status
        self._visto = 0
        self._ligado = None
        self._ev = None

    def iniciar(self, intervalo_ms=1000):
        self._visto = self._loc.contador
        self._ligado = None
        if not self._loc.iniciar(self._atividade, intervalo_ms):
            print("[gps] nao foi possivel assinar o GPS")
        if self._sat is not None:
            try:
                self._sat.iniciar(self._atividade)
            except Exception as e:  # contar satélites é extra: nunca derruba o GPS
                print("[gps] contador de satelites falhou:", e)
                self._sat = None
        if self._aprox is not None:
            try:
                self._aprox_visto = self._aprox.contador
                if not self._aprox.iniciar(self._atividade, 4000):
                    print("[gps] posicao aproximada: sem provedor de rede", self._aprox.erro)
            except Exception as e:  # é um extra: nunca derruba o GPS
                print("[gps] posicao aproximada falhou:", e)
                self._aprox = None
        if self._ev is None:
            self._ev = Clock.schedule_interval(self._conferir, CONFERIR_S)

    def parar(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None
        self._loc.parar(self._atividade)
        if self._aprox is not None:
            self._aprox.parar(self._atividade)
        if self._sat is not None:
            self._sat.parar(self._atividade)

    def _conferir(self, dt):
        loc = self._loc
        ligado = loc.gpsLigado
        if ligado >= 0 and ligado != self._ligado:
            self._ligado = ligado
            self._ao_status("provider-enabled" if ligado else "provider-disabled", PROVEDOR)
        dados = self.ler()
        if dados is not None:
            self._ao_receber(**dados)
        aprox = self._aprox
        if aprox is not None and aprox.contador != self._aprox_visto:
            self._aprox_visto = aprox.contador
            self._ao_aproximada(aprox.lat, aprox.lon, aprox.precisao, aprox.idade, str(aprox.fonte))

    def ler(self):
        """Posição nova desde a última leitura (dict) ou None. Usado pelo
        Clock (app aberto) e pela thread de segundo plano (app minimizado)."""
        loc = self._loc
        n = loc.contador
        if n == self._visto:
            return None
        # lê os campos; se chegou outra posição no meio da leitura, lê de novo
        for _ in range(3):
            dados = dict(lat=loc.lat, lon=loc.lon,
                         # sem velocidade no fix: None (o app mantém a última), não 0
                         speed=loc.velocidade if loc.temVelocidade else None,
                         bearing=loc.rumo if loc.temRumo else None,
                         accuracy=loc.precisao,
                         # para o filtro do velocímetro (filtro.py)
                         speed_acc=loc.precisaoVelocidade if loc.precisaoVelocidade > 0 else None,
                         t=loc.tempo if loc.tempo > 0 else None,
                         age=loc.idade if loc.idade >= 0 else None)
            depois = loc.contador
            if depois == n:
                break
            n = depois
        self._visto = n
        return dados

    def satelites(self):
        """(vistos, em uso) agora, ou None se o contador não existir."""
        if self._sat is None:
            return None
        return self._sat.vistos, self._sat.usados
