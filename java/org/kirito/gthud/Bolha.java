package org.kirito.gthud;

import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * Bolha flutuante (como a da 99): com o app minimizado e rota ativa, fica
 * por cima dos outros apps mostrando os minutos e os km até o destino.
 * Dá para arrastar; tocar abre o GT-HUD de novo. Precisa da permissão
 * "Exibir sobre outros apps" (a pessoa libera uma vez nos Ajustes).
 * Tudo que mexe na tela roda na thread principal do Android (Handler).
 */
public class Bolha {
    private static final Handler principal = new Handler(Looper.getMainLooper());
    private static WindowManager wm;
    private static WindowManager.LayoutParams lp;
    private static LinearLayout vista;
    private static TextView linha1;
    private static TextView linha2;
    private static volatile String texto1 = "";
    private static volatile String texto2 = "";

    public static boolean temPermissao(Context c) {
        return Build.VERSION.SDK_INT < 23 || Settings.canDrawOverlays(c);
    }

    /** Abre a tela do Android "Exibir sobre outros apps" deste app. */
    public static void pedirPermissao(Context c) {
        Intent i = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:" + c.getPackageName()));
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        c.startActivity(i);
    }

    private static int dp(Context c, float v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v,
                c.getResources().getDisplayMetrics());
    }

    public static void mostrar(final Context contexto) {
        final Context c = contexto.getApplicationContext();
        principal.post(new Runnable() {
            @Override
            public void run() {
                if (vista != null || !temPermissao(c)) {
                    return;
                }
                try {
                    criar(c);
                    wm.addView(vista, lp);
                } catch (Exception e) {
                    vista = null;
                }
            }
        });
    }

    public static void atualizar(String a, String b) {
        texto1 = a;
        texto2 = b;
        principal.post(new Runnable() {
            @Override
            public void run() {
                if (linha1 != null) {
                    linha1.setText(texto1);
                    linha2.setText(texto2);
                }
            }
        });
    }

    public static void esconder() {
        principal.post(new Runnable() {
            @Override
            public void run() {
                if (vista != null && wm != null) {
                    try {
                        wm.removeView(vista);
                    } catch (Exception e) {
                        // já tinha saído
                    }
                }
                vista = null;
                linha1 = linha2 = null;
            }
        });
    }

    /** Toque na bolha: o GT-HUD volta para a frente (a permissão de
     *  sobrepor apps também libera abrir a tela vindo do segundo plano). */
    private static void abrirApp(Context c) {
        try {
            Intent abrir = c.getPackageManager().getLaunchIntentForPackage(c.getPackageName());
            if (abrir != null) {
                abrir.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT
                        | Intent.FLAG_ACTIVITY_SINGLE_TOP);
                c.startActivity(abrir);
            }
        } catch (Exception e) {
            // nada: a notificação também abre o app
        }
    }

    private static void criar(final Context c) {
        wm = (WindowManager) c.getSystemService(Context.WINDOW_SERVICE);
        vista = new LinearLayout(c);
        vista.setOrientation(LinearLayout.VERTICAL);
        vista.setGravity(Gravity.CENTER);
        vista.setPadding(dp(c, 14), dp(c, 8), dp(c, 14), dp(c, 8));
        GradientDrawable fundo = new GradientDrawable();
        fundo.setColor(Color.parseColor("#E6050A10"));
        fundo.setCornerRadius(dp(c, 18));
        fundo.setStroke(dp(c, 2), Color.parseColor("#00E5FF"));
        vista.setBackground(fundo);
        linha1 = new TextView(c);
        linha1.setTextColor(Color.parseColor("#00E5FF"));
        linha1.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        linha1.setTypeface(Typeface.DEFAULT_BOLD);
        linha1.setGravity(Gravity.CENTER);
        linha1.setText(texto1);
        linha2 = new TextView(c);
        linha2.setTextColor(Color.WHITE);
        linha2.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        linha2.setGravity(Gravity.CENTER);
        linha2.setText(texto2);
        vista.addView(linha1);
        vista.addView(linha2);

        int tipo = Build.VERSION.SDK_INT >= 26
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE;
        lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
                tipo, WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE, PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        lp.x = c.getResources().getDisplayMetrics().widthPixels - dp(c, 120);
        lp.y = dp(c, 160);

        vista.setOnTouchListener(new View.OnTouchListener() {
            private int x0, y0;
            private float tx0, ty0;
            private boolean arrastou;

            @Override
            public boolean onTouch(View v, MotionEvent e) {
                switch (e.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        x0 = lp.x;
                        y0 = lp.y;
                        tx0 = e.getRawX();
                        ty0 = e.getRawY();
                        arrastou = false;
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        int dx = (int) (e.getRawX() - tx0);
                        int dy = (int) (e.getRawY() - ty0);
                        if (Math.abs(dx) + Math.abs(dy) > dp(c, 8)) {
                            arrastou = true;
                        }
                        lp.x = x0 + dx;
                        lp.y = y0 + dy;
                        try {
                            wm.updateViewLayout(vista, lp);
                        } catch (Exception ex) {
                            // a bolha saiu no meio do arrasto
                        }
                        return true;
                    case MotionEvent.ACTION_UP:
                        if (!arrastou) {
                            abrirApp(c);
                        }
                        return true;
                    default:
                        return false;
                }
            }
        });
    }
}
