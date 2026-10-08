package org.kirito.gthud;

import android.content.Context;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Looper;
import android.os.SystemClock;

/**
 * Posição APROXIMADA, na hora (pedido do dono em 08/10/2026: "às vezes demora
 * muito para achar um satélite; o Waze, o Maps e o Uber funcionam em qualquer
 * lugar"). Eles não esperam o satélite: mostram primeiro onde o celular acha
 * que está pelas redes Wi-Fi e antenas por perto, e pela última posição que o
 * Android guardou. Esta classe faz o mesmo:
 *  - ao iniciar, entrega a última posição conhecida (de qualquer provedor);
 *  - depois, as posições por rede (ou a "fundida" do Android 12+).
 *
 * Fica SEPARADA de Localizacao.java (só satélite) de propósito: posição por
 * rede vem sem velocidade e pula, não serve para o velocímetro nem para a
 * navegação curva a curva. O app só usa esta enquanto o satélite não chega.
 * O Python confere o "contador", como em Localizacao.
 */
public class LocalizacaoAprox implements LocationListener {
    public static volatile int contador = 0;
    public static volatile double lat = 0;
    public static volatile double lon = 0;
    public static volatile double precisao = 9999;   // m
    public static volatile double idade = 0;         // s: há quanto tempo a posição foi medida
    public static volatile String fonte = "";       // "ultima", "network", "fused"...
    public static volatile String erro = "";

    private static LocalizacaoAprox instancia;

    private static void guardar(Location loc, String origem) {
        if (loc == null) {
            return;
        }
        lat = loc.getLatitude();
        lon = loc.getLongitude();
        precisao = loc.hasAccuracy() ? loc.getAccuracy() : 9999;
        idade = (SystemClock.elapsedRealtimeNanos() - loc.getElapsedRealtimeNanos()) / 1e9;
        fonte = origem;
        contador++;  // por último: o Python só lê quando isto muda
    }

    @Override
    public void onLocationChanged(Location loc) {
        guardar(loc, loc.getProvider() == null ? "rede" : loc.getProvider());
    }

    @Override
    public void onProviderEnabled(String provedor) {
    }

    @Override
    public void onProviderDisabled(String provedor) {
    }

    @Override
    public void onStatusChanged(String provedor, int status, Bundle extras) {
        // só existe para os Android antigos (antes do 10 era obrigatório)
    }

    /** Precisa da permissão de localização já liberada. */
    public static boolean iniciar(Context ctx, long intervaloMs) {
        boolean assinou = false;
        try {
            LocationManager lm = (LocationManager) ctx.getSystemService(Context.LOCATION_SERVICE);
            if (instancia == null) {
                instancia = new LocalizacaoAprox();
            }
            // 1) a última posição que o Android guardou: a mais recente entre os provedores
            Location melhor = null;
            for (String p : new String[] {"fused", LocationManager.GPS_PROVIDER,
                                          LocationManager.NETWORK_PROVIDER, LocationManager.PASSIVE_PROVIDER}) {
                try {
                    Location l = lm.getLastKnownLocation(p);
                    if (l != null && (melhor == null
                            || l.getElapsedRealtimeNanos() > melhor.getElapsedRealtimeNanos())) {
                        melhor = l;
                    }
                } catch (Exception e) {
                    // provedor que este celular não tem: segue
                }
            }
            guardar(melhor, "ultima");
            // 2) posições novas por rede; no Android 12+ a "fundida" (Wi-Fi + antenas + sensores)
            String[] provedores = Build.VERSION.SDK_INT >= 31
                    ? new String[] {"fused", LocationManager.NETWORK_PROVIDER}
                    : new String[] {LocationManager.NETWORK_PROVIDER};
            for (String p : provedores) {
                try {
                    if (lm.getAllProviders().contains(p)) {
                        lm.requestLocationUpdates(p, intervaloMs, 0f, instancia, Looper.getMainLooper());
                        assinou = true;
                    }
                } catch (Exception e) {
                    erro = p + ": " + e;
                }
            }
        } catch (Exception e) {
            erro = String.valueOf(e);
        }
        return assinou;
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
