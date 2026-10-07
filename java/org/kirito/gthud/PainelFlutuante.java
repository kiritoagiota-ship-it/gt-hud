package org.kirito.gthud;

import android.content.Context;
import android.content.Intent;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.text.TextPaint;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;

/**
 * Painel flutuante da navegação (pedido do dono, 07/10/2026): com o app
 * minimizado numa rota, um retângulo no meio da tela, por cima de qualquer
 * app, mostra para onde ele está indo e a velocidade:
 *
 *   +--------------+  200 m
 *   |   desenho    |  Vire à direita
 *   |   da rota    |  Rua 5
 *   |   à frente   |  32 km/h
 *   +--------------+  8 min · 2,3 km · 15:44
 *
 * O desenho da esquerda é o caminho dos próximos ~260 m visto de cima, com a
 * frente para cima e a seta na posição da pessoa (o mapa de verdade só existe
 * dentro do app; aqui vai o traçado da rota, que é o que importa para saber
 * a próxima curva). Dá para arrastar; tocar abre o GT-HUD.
 *
 * Usa a mesma permissão da bolha ("Exibir sobre outros apps"). Quem manda os
 * dados é o Python (segundo_plano.py), uma vez por segundo. Tudo que mexe na
 * tela roda na thread principal do Android.
 */
public class PainelFlutuante {
    private static final Handler principal = new Handler(Looper.getMainLooper());
    private static final float METROS_A_FRENTE = 260f;
    private static final float METROS_ATRAS = 60f;

    private static WindowManager wm;
    private static WindowManager.LayoutParams lp;
    private static Vista vista;

    private static volatile String distancia = "";
    private static volatile String instrucao = "";
    private static volatile String rua = "";
    private static volatile String velocidade = "0";
    private static volatile String resto = "";
    private static volatile float[] rota = new float[0];   // x, y em metros (x = direita, y = frente)
    private static volatile boolean claro = false;
    private static volatile int alerta = 0;                 // 0 normal, 1 laranja, 2 vermelho

    public static void mostrar(final Context contexto) {
        final Context c = contexto.getApplicationContext();
        principal.post(new Runnable() {
            @Override
            public void run() {
                if (vista != null || !Bolha.temPermissao(c)) {
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

    /** pontos: "x,y;x,y;..." em metros inteiros (frente = +y, origem = a pessoa). */
    public static void atualizar(String novaDistancia, String novaInstrucao, String novaRua,
                                 String novaVelocidade, String novoResto, String pontos,
                                 boolean temaClaro, int nivelAlerta) {
        distancia = novaDistancia == null ? "" : novaDistancia;
        instrucao = novaInstrucao == null ? "" : novaInstrucao;
        rua = novaRua == null ? "" : novaRua;
        velocidade = novaVelocidade == null ? "" : novaVelocidade;
        resto = novoResto == null ? "" : novoResto;
        claro = temaClaro;
        alerta = nivelAlerta;
        rota = ler(pontos);
        principal.post(new Runnable() {
            @Override
            public void run() {
                if (vista != null) {
                    vista.invalidate();
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
            }
        });
    }

    private static float[] ler(String pontos) {
        if (pontos == null || pontos.length() == 0) {
            return new float[0];
        }
        try {
            String[] pares = pontos.split(";");
            float[] v = new float[pares.length * 2];
            int n = 0;
            for (String par : pares) {
                int virgula = par.indexOf(',');
                if (virgula <= 0) {
                    continue;
                }
                v[n++] = Float.parseFloat(par.substring(0, virgula));
                v[n++] = Float.parseFloat(par.substring(virgula + 1));
            }
            if (n == v.length) {
                return v;
            }
            float[] menor = new float[n];
            System.arraycopy(v, 0, menor, 0, n);
            return menor;
        } catch (Exception e) {
            return new float[0];
        }
    }

    private static float dp(Context c, float v) {
        return TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, c.getResources().getDisplayMetrics());
    }

    private static float sp(Context c, float v) {
        return TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, v, c.getResources().getDisplayMetrics());
    }

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
        vista = new Vista(c);
        int tipo = Build.VERSION.SDK_INT >= 26
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE;
        lp = new WindowManager.LayoutParams(
                (int) dp(c, 306), (int) dp(c, 150),
                tipo, WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE, PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.CENTER;   // no meio da tela; arrastar muda x e y a partir daí
        lp.x = 0;
        lp.y = 0;

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
                            // o painel saiu no meio do arrasto
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

    /** O desenho do painel (tudo no Canvas: sem layout, sem imagens). */
    private static class Vista extends View {
        private final Paint tinta = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final TextPaint letra = new TextPaint(Paint.ANTI_ALIAS_FLAG);
        private final Path caminho = new Path();
        private final RectF caixa = new RectF();

        Vista(Context c) {
            super(c);
        }

        private void texto(Canvas tela, String s, float x, float base, float tamanho, int cor,
                           boolean negrito, float largura) {
            letra.setTextSize(tamanho);
            letra.setColor(cor);
            letra.setTypeface(negrito ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
            CharSequence cabe = TextUtils.ellipsize(s, letra, largura, TextUtils.TruncateAt.END);
            tela.drawText(cabe, 0, cabe.length(), x, base, letra);
        }

        @Override
        protected void onDraw(Canvas tela) {
            super.onDraw(tela);
            try {
                desenhar(tela);
            } catch (Exception e) {
                // desenho é detalhe: nunca derruba o painel
            }
        }

        private void desenhar(Canvas tela) {
            Context c = getContext();
            float w = getWidth(), h = getHeight();
            int destaque = Color.parseColor(claro ? "#00788F" : "#00E5FF");
            int fundo = Color.parseColor(claro ? "#F7FFFFFF" : "#F2060B12");
            int forte = Color.parseColor(claro ? "#0A1A24" : "#F2FBFF");
            int fraco = Color.parseColor(claro ? "#4A6B78" : "#7FB8C6");
            int borda = alerta >= 2 ? Color.parseColor(claro ? "#D01F40" : "#FF3355")
                    : alerta == 1 ? Color.parseColor(claro ? "#C85A00" : "#FF8A00") : destaque;
            float m = dp(c, 2);

            // corpo
            caixa.set(m, m, w - m, h - m);
            tinta.setStyle(Paint.Style.FILL);
            tinta.setColor(fundo);
            tela.drawRoundRect(caixa, dp(c, 16), dp(c, 16), tinta);
            tinta.setStyle(Paint.Style.STROKE);
            tinta.setStrokeWidth(dp(c, 2));
            tinta.setColor(borda);
            tela.drawRoundRect(caixa, dp(c, 16), dp(c, 16), tinta);

            // --- esquerda: o caminho à frente ---
            float lado = h - dp(c, 24);
            float qx = dp(c, 12), qy = dp(c, 12);
            caixa.set(qx, qy, qx + lado, qy + lado);
            tinta.setStyle(Paint.Style.FILL);
            tinta.setColor(Color.parseColor(claro ? "#12000000" : "#16FFFFFF"));
            tela.drawRoundRect(caixa, dp(c, 10), dp(c, 10), tinta);

            float escala = lado / (METROS_A_FRENTE + METROS_ATRAS);
            float ox = qx + lado / 2f;
            float oy = qy + lado - METROS_ATRAS * escala;
            float[] p = rota;
            tela.save();
            tela.clipRect(caixa);
            if (p.length >= 4) {
                caminho.reset();
                caminho.moveTo(ox + p[0] * escala, oy - p[1] * escala);
                for (int k = 2; k + 1 < p.length; k += 2) {
                    caminho.lineTo(ox + p[k] * escala, oy - p[k + 1] * escala);
                }
                tinta.setStyle(Paint.Style.STROKE);
                tinta.setStrokeCap(Paint.Cap.ROUND);
                tinta.setStrokeJoin(Paint.Join.ROUND);
                tinta.setStrokeWidth(dp(c, 9));
                tinta.setColor((destaque & 0x00FFFFFF) | 0x44000000);
                tela.drawPath(caminho, tinta);
                tinta.setStrokeWidth(dp(c, 4.5f));
                tinta.setColor(destaque);
                tela.drawPath(caminho, tinta);
            }
            // a seta da pessoa
            float s = dp(c, 9);
            caminho.reset();
            caminho.moveTo(ox, oy - s * 1.25f);
            caminho.lineTo(ox + s * 0.85f, oy + s * 0.85f);
            caminho.lineTo(ox, oy + s * 0.35f);
            caminho.lineTo(ox - s * 0.85f, oy + s * 0.85f);
            caminho.close();
            tinta.setStyle(Paint.Style.FILL);
            tinta.setColor(forte);
            tela.drawPath(caminho, tinta);
            tinta.setStyle(Paint.Style.STROKE);
            tinta.setStrokeWidth(dp(c, 1.6f));
            tinta.setColor(destaque);
            tela.drawPath(caminho, tinta);
            tela.restore();

            // --- direita: curva, rua, velocidade, chegada ---
            float x = qx + lado + dp(c, 12);
            float larg = w - x - dp(c, 12);
            texto(tela, distancia, x, dp(c, 38), sp(c, 26), forte, true, larg);
            texto(tela, instrucao, x, dp(c, 60), sp(c, 15), forte, false, larg);
            texto(tela, rua, x, dp(c, 79), sp(c, 13), destaque, true, larg);

            letra.setTextSize(sp(c, 28));
            letra.setTypeface(Typeface.DEFAULT_BOLD);
            float largVel = letra.measureText(velocidade);
            texto(tela, velocidade, x, dp(c, 116), sp(c, 28), alerta >= 1 ? borda : destaque, true, larg);
            texto(tela, "km/h", x + largVel + dp(c, 5), dp(c, 116), sp(c, 12), fraco, false,
                    Math.max(0f, larg - largVel - dp(c, 5)));
            texto(tela, resto, x, dp(c, 137), sp(c, 12.5f), fraco, false, larg);
        }
    }
}
