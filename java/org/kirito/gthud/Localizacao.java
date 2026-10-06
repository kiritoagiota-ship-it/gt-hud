package org.kirito.gthud;

import android.content.Context;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Looper;

/**
 * Recebe as posições do GPS (só satélite) e guarda a última em campos
 * estáticos; o Python confere o "contador" algumas vezes por segundo e lê
 * os valores quando ele muda.
 *
 * Por que em Java: desde o Android 12 o sistema entrega as posições pelo
 * onLocationChanged(List<Location>), um método "default" da interface que,
 * em Java, repassa cada posição para o onLocationChanged(Location). O
 * ouvinte feito em Python (pyjnius, e o plyer também) é um Proxy, e Proxy
 * não executa método default: as posições se perdiam no caminho e o painel
 * ficava "Buscando GPS" com dezenas de satélites no céu aberto.
 */
public class Localizacao implements LocationListener {
    public static volatile int contador = 0;
    public static volatile double lat = 0;
    public static volatile double lon = 0;
    public static volatile double velocidade = 0;      // m/s
    public static volatile boolean temVelocidade = false;
    public static volatile double precisao = 0;        // m
    public static volatile double rumo = 0;            // graus, 0 = norte, horário
    public static volatile boolean temRumo = false;
    public static volatile int gpsLigado = -1;         // -1 = não sabe, 0 = não, 1 = sim
    // para o filtro do velocímetro: o quanto o GPS confia na velocidade
    // (m/s; -1 = não informou) e a hora exata da leitura (s desde o boot)
    public static volatile double precisaoVelocidade = -1;
    public static volatile double tempo = 0;

    private static Localizacao instancia;

    @Override
    public void onLocationChanged(Location loc) {
        lat = loc.getLatitude();
        lon = loc.getLongitude();
        temVelocidade = loc.hasSpeed();
        velocidade = loc.hasSpeed() ? loc.getSpeed() : 0;
        precisao = loc.hasAccuracy() ? loc.getAccuracy() : 9999;
        temRumo = loc.hasBearing();
        rumo = loc.hasBearing() ? loc.getBearing() : 0;
        double pv = -1;
        if (Build.VERSION.SDK_INT >= 26 && loc.hasSpeedAccuracy()) {
            pv = loc.getSpeedAccuracyMetersPerSecond();
        }
        precisaoVelocidade = pv;
        tempo = loc.getElapsedRealtimeNanos() / 1e9;
        contador++;  // por último: o Python só lê quando isto muda
    }

    @Override
    public void onProviderEnabled(String provedor) {
        gpsLigado = 1;
    }

    @Override
    public void onProviderDisabled(String provedor) {
        gpsLigado = 0;
    }

    @Override
    public void onStatusChanged(String provedor, int status, Bundle extras) {
        // só existe para os Android antigos (antes do 10 era obrigatório)
    }

    /** Precisa da permissão de localização precisa já liberada. */
    public static boolean iniciar(Context ctx, long intervaloMs) {
        try {
            LocationManager lm = (LocationManager) ctx.getSystemService(Context.LOCATION_SERVICE);
            if (instancia == null) {
                instancia = new Localizacao();
            }
            gpsLigado = lm.isProviderEnabled(LocationManager.GPS_PROVIDER) ? 1 : 0;
            lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, intervaloMs, 0f,
                    instancia, Looper.getMainLooper());
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    public static void parar(Context ctx) {
        try {
            if (instancia != null) {
                LocationManager lm = (LocationManager) ctx.getSystemService(Context.LOCATION_SERVICE);
                lm.removeUpdates(instancia);
            }
        } catch (Exception e) {
            // nada a fazer
        }
    }
}
