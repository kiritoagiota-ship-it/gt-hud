"""Fonte de posição: GPS real no Android ou simulador no PC.

ATENÇÃO: no Android as leituras chegam na thread de UI do Android, que NÃO
é a thread do Kivy. Por isso tudo passa por @mainthread antes de chegar nas
telas.
"""
from kivy.clock import mainthread
from kivy.utils import platform


class ServicoGPS:
    def __init__(self, ao_receber, ao_status=None):
        self.ao_receber = ao_receber
        self.ao_status = ao_status
        self.ativo = False
        self.modo = None  # "GPS" ou "SIM"
        self._gps = None
        self._sim = None

    def iniciar(self, usar_simulador=False):
        if self.ativo:
            return
        if usar_simulador or platform != "android":
            from simulador import SimuladorGPS
            self._sim = SimuladorGPS(self._on_location)
            self._sim.iniciar()
            self.modo = "SIM"
        else:
            from gps_android import GPSAndroid
            self._gps = GPSAndroid(self._on_location, self._on_status)
            self._gps.iniciar(intervalo_ms=1000)
            self.modo = "GPS"
        self.ativo = True

    def parar(self):
        if self._sim:
            self._sim.parar()
            self._sim = None
        if self._gps:
            try:
                self._gps.parar()
            except Exception:
                pass
            self._gps = None
        self.ativo = False

    def reiniciar(self, usar_simulador):
        self.parar()
        self.iniciar(usar_simulador)

    @mainthread
    def _on_location(self, **dados):
        self.ao_receber(dados)

    @mainthread
    def _on_status(self, tipo, status):
        if self.ao_status:
            self.ao_status(tipo, status)
