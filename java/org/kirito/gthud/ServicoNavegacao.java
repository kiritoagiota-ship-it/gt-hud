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
    private static volatile int progresso = -1;       // 0..100 da rota; -1 = sem barra
    private static volatile boolean claro = false;    // tema do app
    private static final String ACAO_ENCERRAR = "org.kirito.gthud.ENCERRAR";
    // o Python ligou o serviço e ainda não desligou: só assim a notificação pode ser (re)posta.
    // (Até a 1.0.70, fechar o app pelos recentes parava o serviço, mas o Python seguia vivo e
    // punha a notificação de volta a cada 2 s: ela "não sumia".)
    private static volatile boolean vivo = false;
    // o dono fechou: tirou o app dos recentes ou tocou em "Encerrar" na notificação
    private static volatile boolean pediuFechar = false;
    private static volatile boolean comBotao = false;  // mostra o botão "Encerrar"
    private PowerManager.WakeLock acordado;

    // --- chamados pelo Python ---------------------------------------------------
    public static void iniciar(Context c) {
        vivo = true;
        pediuFechar = false;
        Intent i = new Intent(c, ServicoNavegacao.class);
        if (Build.VERSION.SDK_INT >= 26) {
            c.startForegroundService(i);
        } else {
            c.startService(i);
        }
    }

    public static void parar(Context c) {
        vivo = false;
        c.stopService(new Intent(c, ServicoNavegacao.class));
        tirarNotificacao(c);
    }

    /** O dono fechou (recentes ou botão "Encerrar")? O Python pergunta e encerra o app. */
    public static boolean fechou() {
        return pediuFechar;
    }

    /** Liga/desliga o botão "Encerrar" da notificação (vale na próxima atualização). */
    public static void botaoEncerrar(boolean ligado) {
        comBotao = ligado;
    }

    private static void tirarNotificacao(Context c) {
        try {
            NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
            nm.cancel(ID);
        } catch (Exception e) {
            // nada: sem a notificação não há o que tirar
        }
    }

    // tema Monarca do app (preto, roxo e azul): vale quando o tema não é o claro
    public static volatile boolean monarca = false;

    /** Liga/desliga as cores do tema Monarca na notificação e na bolha. */
    public static void temaMonarca(boolean ligado) {
        monarca = ligado;
        Bolha.temaMonarca(ligado);
    }

    /** Tema do app e quanto da rota já foi feito: valem na próxima atualização. */
    public static void estilo(boolean temaClaro, int feito) {
        claro = temaClaro;
        progresso = feito;
        Bolha.estilo(temaClaro, feito);
    }

    public static void atualizar(Context c, String novoTitulo, String novoTexto) {
        titulo = novoTitulo;
        texto = novoTexto;
        if (!vivo) {
            return;   // serviço parado: nada de pôr a notificação de volta
        }
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
        if (intent != null && ACAO_ENCERRAR.equals(intent.getAction())) {
            // botão "Encerrar" da notificação: para tudo; o Python vê fechou() e fecha o app
            pediuFechar = true;
            vivo = false;
            stopSelf();
            tirarNotificacao(this);
            return START_NOT_STICKY;
        }
        try {
            Notification n = montar(this);
            if (Build.VERSION.SDK_INT >= 29) {
                startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
            } else {
                startForeground(ID, n);
            }
        } catch (Exception e) {
            // o Android recusou (ex.: o app já tinha saído da tela): desiste em vez de derrubar o app
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        // fechou o app pela lista de recentes: some com a notificação (e o Python encerra o app)
        pediuFechar = true;
        vivo = false;
        stopSelf();
        tirarNotificacao(this);
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        vivo = false;
        if (acordado != null && acordado.isHeld()) {
            acordado.release();
        }
        Bolha.esconder();
        PainelFlutuante.esconder();
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
        b.setColor(claro ? 0xFF00788F : (monarca ? 0xFF5AA0FF : 0xFF00E5FF));
        if (comBotao) {
            Intent encerrar = new Intent(c, ServicoNavegacao.class);
            encerrar.setAction(ACAO_ENCERRAR);
            b.addAction(0, "Encerrar", PendingIntent.getService(c, 1, encerrar,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        }
        if (progresso >= 0) {
            b.setProgress(100, Math.min(100, progresso), false);   // barra: quanto da rota já foi
        }
        if (Build.VERSION.SDK_INT >= 31) {
            b.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE);
        }
        return b.build();
    }
}
