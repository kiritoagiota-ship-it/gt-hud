"""GPS real do Android, ouvindo só o satélite.

O plyer.gps assina TODOS os provedores de localização (gps, network,
passive...). O de rede (wi-fi/antena) chega com precisão de 15-20 m, que
passa no filtro, mas sem velocidade (vira 0 km/h) e com a posição pulando:
o velocímetro caía para 0 no meio do movimento e a distância somava pulos.
Aqui só o provedor "gps" é assinado (mesmo mecanismo do plyer, via pyjnius).

Só é importado no Android (jnius não existe no PC).
"""
from jnius import PythonJavaClass, autoclass, java_method

Context = autoclass("android.content.Context")
Looper = autoclass("android.os.Looper")
PythonActivity = autoclass("org.kivy.android.PythonActivity")

PROVEDOR = "gps"


class _Ouvinte(PythonJavaClass):
    __javainterfaces__ = ["android/location/LocationListener"]

    def __init__(self, ao_receber, ao_status):
        self.ao_receber = ao_receber
        self.ao_status = ao_status
        super().__init__()

    @java_method("(Landroid/location/Location;)V")
    def onLocationChanged(self, loc):
        self.ao_receber(
            lat=loc.getLatitude(), lon=loc.getLongitude(),
            # sem velocidade no fix: None (o app mantém a última), não 0
            speed=loc.getSpeed() if loc.hasSpeed() else None,
            bearing=loc.getBearing(), altitude=loc.getAltitude(),
            accuracy=loc.getAccuracy())

    @java_method("(Ljava/lang/String;)V")
    def onProviderEnabled(self, provedor):
        self.ao_status("provider-enabled", provedor)

    @java_method("(Ljava/lang/String;)V")
    def onProviderDisabled(self, provedor):
        self.ao_status("provider-disabled", provedor)

    @java_method("(Ljava/lang/String;ILandroid/os/Bundle;)V")
    def onStatusChanged(self, provedor, status, extras):
        pass


def _classe_satelites():
    """java/org/kirito/gthud/Satelites.java (conta satélites); None se faltar."""
    try:
        return autoclass("org.kirito.gthud.Satelites")
    except Exception as e:
        print("[gps] sem contador de satelites:", e)
        return None


class GPSAndroid:
    def __init__(self, ao_receber, ao_status):
        self._atividade = PythonActivity.mActivity
        self._lm = self._atividade.getSystemService(Context.LOCATION_SERVICE)
        # a referência precisa ficar guardada, senão o Python recolhe o ouvinte
        self._ouvinte = _Ouvinte(ao_receber, ao_status)
        self._sat = _classe_satelites()

    def iniciar(self, intervalo_ms=1000):
        self._lm.requestLocationUpdates(PROVEDOR, intervalo_ms, 0, self._ouvinte,
                                        Looper.getMainLooper())
        # nem todo Android avisa na hora que a Localização já estava desligada
        if not self._lm.isProviderEnabled(PROVEDOR):
            self._ouvinte.ao_status("provider-disabled", PROVEDOR)
        if self._sat is not None:
            try:
                self._sat.iniciar(self._atividade)
            except Exception as e:  # contar satélites é extra: nunca derruba o GPS
                print("[gps] contador de satelites falhou:", e)
                self._sat = None

    def parar(self):
        self._lm.removeUpdates(self._ouvinte)
        if self._sat is not None:
            self._sat.parar(self._atividade)

    def satelites(self):
        """(vistos, em uso) agora, ou None se o contador não existir."""
        if self._sat is None:
            return None
        return self._sat.vistos, self._sat.usados
