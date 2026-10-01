package org.kirito.gthud;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

/**
 * Serviço "de primeiro plano" (tipo localização) enquanto há rota ativa:
 * com ele o Android deixa o GPS mandar posição 1x/s e não mata o app quando
 * ele é minimizado ou a tela apaga. Mostra a notificação fixa com km,
 * minutos e a próxima curva; tocar nela abre o app.
 *
 * Quem faz a navegação continua sendo o Python (segundo_plano.py); aqui é só
 * o "passe livre" do Android + a notificação + manter a CPU acordada.
 * Declarado no AndroidManifest pelo build (ver .github/workflows/build.yml).
 */
public class ServicoNavegacao extends Service {
    private static final String CANAL = "navegacao";
    private static final int ID = 7001;
    private static volatile String titulo = "GT-HUD navegando";
    private static volatile String texto = "";
    private PowerManager.WakeLock acordado;

    // --- chamados pelo Python ---------------------------------------------------
    public static void iniciar(Context c) {
        Intent i = new Intent(c, ServicoNavegacao.class);
        if (Build.VERSION.SDK_INT >= 26) {
            c.startForegroundService(i);
        } else {
            c.startService(i);
        }
    }

    public static void parar(Context c) {
        c.stopService(new Intent(c, ServicoNavegacao.class));
    }

    public static void atualizar(Context c, String novoTitulo, String novoTexto) {
        titulo = novoTitulo;
        texto = novoTexto;
        try {
            NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
            nm.notify(ID, montar(c));
        } catch (Exception e) {
            // sem permissão de notificação: o serviço segue funcionando
        }
    }

    // --- serviço -----------------------------------------------------------------
    @Override
    public void onCreate() {
        super.onCreate();
        criarCanal(this);
        try {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            acordado = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "gthud:navegacao");
            acordado.acquire(6 * 60 * 60 * 1000L);  // no máximo 6 h, por segurança
        } catch (Exception e) {
            acordado = null;
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Notification n = montar(this);
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
        } else {
            startForeground(ID, n);
        }
        return START_NOT_STICKY;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        // fechou o app pela lista de recentes: some com a notificação
        stopSelf();
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        if (acordado != null && acordado.isHeld()) {
            acordado.release();
        }
        Bolha.esconder();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    // --- notificação ---------------------------------------------------------------
    private static void criarCanal(Context c) {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel canal = new NotificationChannel(CANAL, "Navegação",
                    NotificationManager.IMPORTANCE_LOW);  // sem som: quem fala é o assistente
            canal.setDescription("Km e minutos até o destino durante a rota");
            canal.setShowBadge(false);
            NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
            nm.createNotificationChannel(canal);
        }
    }

    static PendingIntent abrirApp(Context c) {
        Intent abrir = c.getPackageManager().getLaunchIntentForPackage(c.getPackageName());
        if (abrir == null) {
            abrir = new Intent();
        }
        abrir.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP
                | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        return PendingIntent.getActivity(c, 0, abrir,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    private static Notification montar(Context c) {
        criarCanal(c);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(c, CANAL) : new Notification.Builder(c);
        b.setContentTitle(titulo)
                .setContentText(texto)
                .setStyle(new Notification.BigTextStyle().bigText(texto))
                .setSmallIcon(c.getApplicationInfo().icon)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setShowWhen(false)
                .setCategory(Notification.CATEGORY_NAVIGATION)
                .setContentIntent(abrirApp(c));
        if (Build.VERSION.SDK_INT >= 31) {
            b.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE);
        }
        return b.build();
    }
}
