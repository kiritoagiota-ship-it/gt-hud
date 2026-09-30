package org.kirito.gthud;

import android.content.Context;
import android.location.GnssStatus;
import android.location.LocationManager;
import android.os.Handler;
import android.os.Looper;

/**
 * Conta os satélites que o GPS está vendo e usando, para o painel mostrar
 * que o GPS está vivo mesmo antes do primeiro sinal bom.
 *
 * GnssStatus.Callback é uma classe (não interface), então não dá para
 * implementar pelo pyjnius: fica aqui em Java e o Python só lê os campos
 * estáticos (vistos/usados) uma vez por segundo, sem callback para o Python.
 */
public class Satelites extends GnssStatus.Callback {
    public static volatile int vistos = 0;
    public static volatile int usados = 0;

    private static Satelites instancia;

    @Override
    public void onSatelliteStatusChanged(GnssStatus status) {
        int total = status.getSatelliteCount();
        int emUso = 0;
        for (int i = 0; i < total; i++) {
            if (status.usedInFix(i)) {
                emUso++;
            }
        }
        vistos = total;
        usados = emUso;
    }

    @Override
    public void onStopped() {
        vistos = 0;
        usados = 0;
    }

    /** Precisa da permissão de localização precisa já liberada. */
    public static boolean iniciar(Context ctx) {
        try {
            LocationManager lm = (LocationManager) ctx.getSystemService(Context.LOCATION_SERVICE);
            if (instancia == null) {
                instancia = new Satelites();
            }
            return lm.registerGnssStatusCallback(instancia, new Handler(Looper.getMainLooper()));
        } catch (Exception e) {
            return false;
        }
    }

    public static void parar(Context ctx) {
        try {
            if (instancia != null) {
                LocationManager lm = (LocationManager) ctx.getSystemService(Context.LOCATION_SERVICE);
                lm.unregisterGnssStatusCallback(instancia);
            }
        } catch (Exception e) {
            // nada a fazer: só deixa de contar
        }
        vistos = 0;
        usados = 0;
    }
}
