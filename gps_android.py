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


class GPSAndroid:
    def __init__(self, ao_receber, ao_status):
        self._lm = PythonActivity.mActivity.getSystemService(Context.LOCATION_SERVICE)
        # a referência precisa ficar guardada, senão o Python recolhe o ouvinte
        self._ouvinte = _Ouvinte(ao_receber, ao_status)

    def iniciar(self, intervalo_ms=1000):
        self._lm.requestLocationUpdates(PROVEDOR, intervalo_ms, 0, self._ouvinte,
                                        Looper.getMainLooper())

    def parar(self):
        self._lm.removeUpdates(self._ouvinte)
