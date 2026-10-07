package org.kirito.gthud;

import android.content.Context;
import android.content.Intent;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.Shader;
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
 * Painel flutuante da navegação: com o app minimizado numa rota, um
 * retângulo no meio da tela, por cima de qualquer app, mostra para onde a
 * pessoa está indo e a velocidade.
 *
 * Visual (08/10/2026, a partir de um desenho que o dono mandou): moldura de
 * HUD com os cantos cortados e brilho em volta; à esquerda um MINI MAPA (as
 * ruas de perto em cinza, a rota em destaque, a seta e uma bússola); à
 * direita a distância até a curva, a instrução, a rua, a velocidade e, numa
 * faixa embaixo, o relógio com tempo, km e hora de chegada.
 *
 * As ruas vêm do Python (mini_mapa.py, dos arquivos de mapa que o app já
 * baixou) e a rota também (segundo_plano.py), nas mesmas coordenadas: metros
 * (leste, norte) a partir de uma âncora. O Python manda 1 posição por
 * segundo; ENTRE elas o mapa segue andando e girando sozinho, sem trancos.
 * Dá para arrastar; tocar abre o GT-HUD. Usa a permissão "Exibir sobre
 * outros apps". Tudo que mexe na tela roda na thread principal do Android.
 */
public class PainelFlutuante {
    private static final Handler principal = new Handler(Looper.getMainLooper());
    private static final float METROS_A_FRENTE = 230f;
    private static final float METROS_ATRAS = 70f;
    private static final float LARGURA_DP = 340f;
    private static final float ALTURA_DP = 166f;

    private static WindowManager wm;
    private static WindowManager.LayoutParams lp;
    private static Vista vista;

    private static volatile String distancia = "";
    private static volatile String instrucao = "";
    private static volatile String rua = "";
    private static volatile String velocidade = "0";
    private static volatile String resto = "";
    // a rota: x, y em metros a partir da âncora; o 1o ponto fica a `distInicio`
    // metros do começo da rota e a pessoa está em `distAqui`, a `velMs`
    private static volatile float[] rota = new float[0];
    private static volatile float[] acumulado = new float[0];
    private static volatile double distInicio = 0;
    private static volatile double distAqui = 0;
    private static volatile float velMs = 0;
    private static volatile long recebidoNs = 0;
    // as ruas de perto (mesma âncora): cada uma com seus pontos e a grossura (1 a 3)
    private static volatile float[][] ruasPontos = new float[0][];
    private static volatile int[] ruasGrossura = new int[0];
    private static volatile boolean claro = false;
    private static volatile int alerta = 0;                 // 0 normal, 1 laranja, 2 vermelho
    // para o diagnóstico (o Python lê): 0 = fechado, 1 = na tela, -1 = não abriu
    public static volatile int estado = 0;
    public static volatile String erro = "";

    public static void mostrar(final Context contexto) {
        final Context c = contexto.getApplicationContext();
        principal.post(new Runnable() {
            @Override
            public void run() {
                if (vista != null) {
                    estado = 1;
                    return;
                }
                if (!Bolha.temPermissao(c)) {
                    estado = -1;
                    erro = "sem a permissao de exibir sobre outros apps";
                    return;
                }
                try {
                    criar(c);
                    wm.addView(vista, lp);
                    estado = 1;
                    erro = "";
                } catch (Throwable e) {
                    vista = null;
                    estado = -1;
                    erro = String.valueOf(e);
                }
            }
        });
    }

    /** pontos: "x,y;x,y;..." em metros (leste, norte) a partir da âncora; o 1o
     *  está a `inicioM` metros do começo da rota; a pessoa está em `aquiM`,
     *  andando a `velocidadeMs`. */
    public static void atualizar(String novaDistancia, String novaInstrucao, String novaRua,
                                 String novaVelocidade, String novoResto, String pontos,
                                 boolean temaClaro, int nivelAlerta,
                                 float inicioM, float aquiM, float velocidadeMs) {
        distancia = novaDistancia == null ? "" : novaDistancia;
        instrucao = novaInstrucao == null ? "" : novaInstrucao;
        rua = novaRua == null ? "" : novaRua;
        velocidade = novaVelocidade == null ? "" : novaVelocidade;
        resto = novoResto == null ? "" : novoResto;
        claro = temaClaro;
        alerta = nivelAlerta;
        float[] novos = ler(pontos, ";");
        float[] soma = new float[novos.length / 2];
        for (int k = 1; k < soma.length; k++) {
            float dx = novos[2 * k] - novos[2 * k - 2];
            float dy = novos[2 * k + 1] - novos[2 * k - 1];
            soma[k] = soma[k - 1] + (float) Math.sqrt(dx * dx + dy * dy);
        }
        acumulado = soma;
        rota = novos;
        distInicio = inicioM;
        distAqui = aquiM;
        velMs = Math.max(0f, velocidadeMs);
        recebidoNs = System.nanoTime();
        principal.post(new Runnable() {
            @Override
            public void run() {
                if (vista != null) {
                    vista.invalidate();
                }
            }
        });
    }

    /** As ruas de perto: "g:x,y x,y x,y;g:x,y x,y;..." (g = grossura 1 a 3;
     *  metros a partir da mesma âncora da rota). Texto vazio = sem ruas. */
    public static void ruas(String dados) {
        try {
            if (dados == null || dados.length() == 0) {
                ruasPontos = new float[0][];
                ruasGrossura = new int[0];
                return;
            }
            String[] linhas = dados.split(";");
            float[][] pontos = new float[linhas.length][];
            int[] grossura = new int[linhas.length];
            int n = 0;
            for (String linha : linhas) {
                int doisPontos = linha.indexOf(':');
                if (doisPontos <= 0) {
                    continue;
                }
                float[] p = ler(linha.substring(doisPontos + 1), " ");
                if (p.length >= 4) {
                    grossura[n] = Integer.parseInt(linha.substring(0, doisPontos));
                    pontos[n] = p;
                    n++;
                }
            }
            float[][] pontosCertos = new float[n][];
            int[] grossuraCerta = new int[n];
            System.arraycopy(pontos, 0, pontosCertos, 0, n);
            System.arraycopy(grossura, 0, grossuraCerta, 0, n);
            ruasGrossura = grossuraCerta;
            ruasPontos = pontosCertos;
        } catch (Exception e) {
            ruasPontos = new float[0][];
            ruasGrossura = new int[0];
        }
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
                estado = 0;
            }
        });
    }

    /** "x,y<sep>x,y<sep>..." -> {x, y, x, y, ...} */
    private static float[] ler(String pontos, String separador) {
        if (pontos == null || pontos.length() == 0) {
            return new float[0];
        }
        try {
            String[] pares = pontos.split(separador);
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
        int larguraTela = c.getResources().getDisplayMetrics().widthPixels;
        int largura = (int) Math.min(dp(c, LARGURA_DP), larguraTela - dp(c, 12));
        lp = new WindowManager.LayoutParams(
                largura, (int) (largura * ALTURA_DP / LARGURA_DP),
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

    /** O desenho do painel (tudo no Canvas: sem layout, sem imagens). As
     *  medidas são em "u": 1 u = largura da janela / LARGURA_DP (1 dp no
     *  tamanho normal; menor se a tela for estreita). */
    private static class Vista extends View {
        private final Paint tinta = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final TextPaint letra = new TextPaint(Paint.ANTI_ALIAS_FLAG);
        private final Path caminho = new Path();
        private final Path moldura = new Path();
        private final float[] ponto = new float[2];
        private double mostrada = -1;     // metros da rota em que a seta está desenhada agora
        private long quadroNs = 0;
        private float u = 1f;
        private LinearGradient degrade;
        private float degradeAltura = -1f;
        private boolean degradeClaro = false;

        Vista(Context c) {
            super(c);
        }

        /** Retângulo com os quatro cantos cortados em `corte`. */
        private void cortado(Path p, float x0, float y0, float x1, float y1, float corte) {
            p.reset();
            p.moveTo(x0 + corte, y0);
            p.lineTo(x1 - corte, y0);
            p.lineTo(x1, y0 + corte);
            p.lineTo(x1, y1 - corte);
            p.lineTo(x1 - corte, y1);
            p.lineTo(x0 + corte, y1);
            p.lineTo(x0, y1 - corte);
            p.lineTo(x0, y0 + corte);
            p.close();
        }

        /** (x, y) do caminho a `s` metros do 1o ponto. */
        private void pontoEm(float[] p, float[] ac, float s) {
            int n = ac.length;
            if (n == 0) {
                ponto[0] = 0f;
                ponto[1] = 0f;
                return;
            }
            if (s <= 0f || n == 1) {
                ponto[0] = p[0];
                ponto[1] = p[1];
                return;
            }
            if (s >= ac[n - 1]) {
                ponto[0] = p[2 * n - 2];
                ponto[1] = p[2 * n - 1];
                return;
            }
            int i = 0;
            while (i < n - 2 && ac[i + 1] < s) {
                i++;
            }
            float trecho = ac[i + 1] - ac[i];
            float f = trecho > 0f ? (s - ac[i]) / trecho : 0f;
            ponto[0] = p[2 * i] + (p[2 * i + 2] - p[2 * i]) * f;
            ponto[1] = p[2 * i + 1] + (p[2 * i + 3] - p[2 * i + 1]) * f;
        }

        private float texto(Canvas tela, String s, float x, float base, float tamanho, int cor,
                            boolean negrito, float largura) {
            letra.setTextSize(tamanho);
            letra.setColor(cor);
            letra.setTypeface(negrito ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
            CharSequence cabe = TextUtils.ellipsize(s, letra, Math.max(0f, largura), TextUtils.TruncateAt.END);
            tela.drawText(cabe, 0, cabe.length(), x, base, letra);
            return letra.measureText(cabe, 0, cabe.length());
        }

        private void linha(Canvas tela, float x0, float y0, float x1, float y1, float grossura, int cor) {
            tinta.setShader(null);
            tinta.setStyle(Paint.Style.STROKE);
            tinta.setStrokeCap(Paint.Cap.ROUND);
            tinta.setStrokeWidth(grossura);
            tinta.setColor(cor);
            tela.drawLine(x0, y0, x1, y1, tinta);
        }

        private static int comAlfa(int cor, int alfa) {
            return (cor & 0x00FFFFFF) | (alfa << 24);
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
            float w = getWidth(), h = getHeight();
            u = w / LARGURA_DP;
            int destaque = Color.parseColor(claro ? "#00788F" : "#19E3FF");
            int forte = Color.parseColor(claro ? "#0A1A24" : "#F2FBFF");
            int suave = Color.parseColor(claro ? "#3F6272" : "#A9DCEA");
            int fundoCima = Color.parseColor(claro ? "#FBFFFFFF" : "#F50C1826");
            int fundoBaixo = Color.parseColor(claro ? "#FBEFF4F7" : "#F505090F");
            int corMapa = Color.parseColor(claro ? "#FFE3EAEF" : "#FF0A131D");
            int corRua = Color.parseColor(claro ? "#FFFFFFFF" : "#FF24364A");
            int corRuaGrande = Color.parseColor(claro ? "#FFFFE9A8" : "#FF2F465F");
            int borda = alerta >= 2 ? Color.parseColor(claro ? "#D01F40" : "#FF3355")
                    : alerta == 1 ? Color.parseColor(claro ? "#C85A00" : "#FF8A00") : destaque;

            // ------------------------------------------------ moldura com brilho
            float m = 7f * u;
            cortado(moldura, m, m, w - m, h - m, 15f * u);
            tinta.setShader(null);
            tinta.setStyle(Paint.Style.STROKE);
            tinta.setStrokeJoin(Paint.Join.ROUND);
            tinta.setStrokeWidth(11f * u);
            tinta.setColor(comAlfa(borda, 0x26));
            tela.drawPath(moldura, tinta);
            tinta.setStrokeWidth(6f * u);
            tinta.setColor(comAlfa(borda, 0x50));
            tela.drawPath(moldura, tinta);
            tinta.setStyle(Paint.Style.FILL);
            if (degrade == null || degradeAltura != h || degradeClaro != claro) {   // (não cria um novo a cada quadro)
                degrade = new LinearGradient(0, m, 0, h - m, fundoCima, fundoBaixo, Shader.TileMode.CLAMP);
                degradeAltura = h;
                degradeClaro = claro;
            }
            // (com degradê, a transparência da tinta ainda vale: sem voltar a cor para
            // opaca, o corpo saía com os 31% da linha de brilho e dava para ver os apps atrás)
            tinta.setColor(Color.BLACK);
            tinta.setShader(degrade);
            tela.drawPath(moldura, tinta);
            tinta.setShader(null);
            tinta.setStyle(Paint.Style.STROKE);
            tinta.setStrokeWidth(2.2f * u);
            tinta.setColor(borda);
            tela.drawPath(moldura, tinta);

            // ------------------------------------------------ mini mapa (esquerda)
            float qx = m + 9f * u, qy = m + 9f * u;
            float lado = h - 2f * (m + 9f * u);
            cortado(caminho, qx, qy, qx + lado, qy + lado, 9f * u);
            tinta.setStyle(Paint.Style.FILL);
            tinta.setColor(corMapa);
            tela.drawPath(caminho, tinta);

            float escala = lado / (METROS_A_FRENTE + METROS_ATRAS);
            float ox = qx + lado * 0.56f;
            float oy = qy + lado - METROS_ATRAS * escala;
            float[] p = rota;
            float[] ac = acumulado;
            boolean animando = false;
            float ux = 0f, uy = 1f, px = 0f, py = 0f;
            boolean temRota = p.length >= 4 && ac.length * 2 == p.length;
            if (temRota) {
                // onde a seta deveria estar AGORA: a última posição recebida mais o que
                // andou desde então; o mapa vai até lá suave, sem pular
                long agora = System.nanoTime();
                float dt = quadroNs == 0 ? 0f : Math.min(0.1f, (agora - quadroNs) / 1e9f);
                quadroNs = agora;
                double alvo = distAqui + velMs * Math.min(2.0, (agora - recebidoNs) / 1e9);
                double erroD = alvo - mostrada;
                if (mostrada < 0 || Math.abs(erroD) > 60) {
                    mostrada = alvo;
                } else {
                    mostrada += Math.max(0.0, velMs + erroD * 1.5) * dt;
                }
                animando = velMs > 0.3f || Math.abs(alvo - mostrada) > 0.5;
                float s = (float) (mostrada - distInicio);
                pontoEm(p, ac, s);
                px = ponto[0];
                py = ponto[1];
                // "frente" = para onde o caminho vai nos próximos metros (vira suave nas curvas)
                pontoEm(p, ac, s - 4f);
                float ax = ponto[0], ay = ponto[1];
                pontoEm(p, ac, s + 14f);
                ux = ponto[0] - ax;
                uy = ponto[1] - ay;
                float tam = (float) Math.sqrt(ux * ux + uy * uy);
                if (tam < 0.01f) {
                    ux = 0f;
                    uy = 1f;
                } else {
                    ux /= tam;
                    uy /= tam;
                }
            }

            tela.save();
            tela.clipPath(caminho);
            tinta.setStrokeCap(Paint.Cap.ROUND);
            tinta.setStrokeJoin(Paint.Join.ROUND);
            if (temRota) {
                // as ruas de perto, da mais fina para a mais grossa
                float[][] ruasP = ruasPontos;
                int[] ruasG = ruasGrossura;
                int nRuas = Math.min(ruasP.length, ruasG.length);
                for (int grossura = 1; grossura <= 3; grossura++) {
                    caminho.reset();
                    for (int r = 0; r < nRuas; r++) {
                        float[] q = ruasP[r];
                        if (ruasG[r] != grossura || q == null) {
                            continue;
                        }
                        for (int k = 0; k + 1 < q.length; k += 2) {
                            float dx = q[k] - px, dy = q[k + 1] - py;
                            float sx = ox + (dx * uy - dy * ux) * escala;
                            float sy = oy - (dx * ux + dy * uy) * escala;
                            if (k == 0) {
                                caminho.moveTo(sx, sy);
                            } else {
                                caminho.lineTo(sx, sy);
                            }
                        }
                    }
                    tinta.setStyle(Paint.Style.STROKE);
                    tinta.setStrokeWidth((3.2f + 1.9f * grossura) * u);
                    tinta.setColor(grossura >= 3 ? corRuaGrande : corRua);
                    tela.drawPath(caminho, tinta);
                }
                // a rota: brilho largo + linha
                caminho.reset();
                for (int k = 0; k + 1 < p.length; k += 2) {
                    float dx = p[k] - px, dy = p[k + 1] - py;
                    float sx = ox + (dx * uy - dy * ux) * escala;
                    float sy = oy - (dx * ux + dy * uy) * escala;
                    if (k == 0) {
                        caminho.moveTo(sx, sy);
                    } else {
                        caminho.lineTo(sx, sy);
                    }
                }
                tinta.setStyle(Paint.Style.STROKE);
                tinta.setStrokeWidth(11f * u);
                tinta.setColor(comAlfa(destaque, 0x40));
                tela.drawPath(caminho, tinta);
                tinta.setStrokeWidth(5.2f * u);
                tinta.setColor(destaque);
                tela.drawPath(caminho, tinta);
            }
            // a seta da pessoa (contorno em destaque, miolo escuro, como no desenho)
            float s9 = 10f * u;
            caminho.reset();
            caminho.moveTo(ox, oy - s9 * 1.35f);
            caminho.lineTo(ox + s9 * 0.9f, oy + s9 * 0.85f);
            caminho.lineTo(ox, oy + s9 * 0.3f);
            caminho.lineTo(ox - s9 * 0.9f, oy + s9 * 0.85f);
            caminho.close();
            tinta.setStyle(Paint.Style.FILL);
            tinta.setColor(claro ? Color.WHITE : Color.parseColor("#FF07111B"));
            tela.drawPath(caminho, tinta);
            tinta.setStyle(Paint.Style.STROKE);
            tinta.setStrokeWidth(2.4f * u);
            tinta.setColor(destaque);
            tela.drawPath(caminho, tinta);
            tela.restore();

            // a borda do mini mapa e a bússola (a agulha aponta o norte)
            cortado(caminho, qx, qy, qx + lado, qy + lado, 9f * u);
            tinta.setStyle(Paint.Style.STROKE);
            tinta.setStrokeWidth(1.2f * u);
            tinta.setColor(comAlfa(destaque, 0xA0));
            tela.drawPath(caminho, tinta);
            float bx = qx + 19f * u, by = qy + 19f * u, br = 11f * u;
            tinta.setStyle(Paint.Style.FILL);
            tinta.setColor(comAlfa(corMapa, 0xE0));
            tela.drawCircle(bx, by, br, tinta);
            tinta.setStyle(Paint.Style.STROKE);
            tinta.setStrokeWidth(1.3f * u);
            tinta.setColor(comAlfa(destaque, 0xC0));
            tela.drawCircle(bx, by, br, tinta);
            tela.save();
            tela.rotate((float) -Math.toDegrees(Math.atan2(ux, uy)), bx, by);
            caminho.reset();
            caminho.moveTo(bx, by - br * 0.72f);
            caminho.lineTo(bx + br * 0.3f, by);
            caminho.lineTo(bx, by + br * 0.72f);
            caminho.lineTo(bx - br * 0.3f, by);
            caminho.close();
            tinta.setStyle(Paint.Style.FILL);
            tinta.setColor(comAlfa(destaque, 0x70));
            tela.drawPath(caminho, tinta);
            caminho.reset();
            caminho.moveTo(bx, by - br * 0.72f);
            caminho.lineTo(bx + br * 0.3f, by);
            caminho.lineTo(bx - br * 0.3f, by);
            caminho.close();
            tinta.setColor(destaque);
            tela.drawPath(caminho, tinta);
            tela.restore();
            if (animando) {
                postInvalidateOnAnimation();   // segue andando até a próxima posição chegar
            }

            // ------------------------------------------------ direita: enfeites da moldura
            float x = qx + lado + 14f * u;
            float fim = w - m - 12f * u;
            float larg = fim - x;
            // risco fino em cima com um degrau, e os dois traços inclinados do canto
            caminho.reset();
            caminho.moveTo(x - 6f * u, qy + 8f * u);
            caminho.lineTo(x + 2f * u, qy);
            caminho.lineTo(x + larg * 0.55f, qy);
            caminho.lineTo(x + larg * 0.55f + 7f * u, qy + 7f * u);
            caminho.lineTo(fim + 2f * u, qy + 7f * u);
            tinta.setStyle(Paint.Style.STROKE);
            tinta.setStrokeWidth(1.1f * u);
            tinta.setColor(comAlfa(destaque, 0x80));
            tela.drawPath(caminho, tinta);
            linha(tela, fim - 16f * u, qy + 11f * u, fim - 9f * u, qy + 18f * u, 2.4f * u, destaque);
            linha(tela, fim - 9f * u, qy + 11f * u, fim - 2f * u, qy + 18f * u, 2.4f * u, comAlfa(destaque, 0x90));
            linha(tela, fim - 12f * u, h - m - 5f * u, fim + 1f * u, h - m - 18f * u, 2.4f * u, comAlfa(destaque, 0x90));
            linha(tela, fim - 4f * u, h - m - 5f * u, fim + 1f * u, h - m - 10f * u, 2.4f * u, destaque);

            // ------------------------------------------------ direita: os textos
            // distância: o número forte e a unidade num tom mais suave ("60" + " m")
            String numero = distancia, unidade = "";
            int espaco = distancia.lastIndexOf(' ');
            if (espaco > 0 && distancia.length() > 0 && Character.isDigit(distancia.charAt(0))) {
                numero = distancia.substring(0, espaco);
                unidade = distancia.substring(espaco + 1);
            }
            float base = qy + 37f * u;
            float andou = texto(tela, numero, x, base, 32f * u, forte, true, larg - 22f * u);
            if (unidade.length() > 0) {
                texto(tela, unidade, x + andou + 5f * u, base, 32f * u, suave, true, larg - andou - 5f * u);
            }
            texto(tela, instrucao, x, qy + 58f * u, 16f * u, forte, true, larg);
            texto(tela, rua, x, qy + 76f * u, 14f * u, destaque, true, larg);
            float largVel = texto(tela, velocidade, x, qy + 106f * u, 28f * u, alerta >= 1 ? borda : destaque,
                    true, larg);
            texto(tela, "km/h", x + largVel + 6f * u, qy + 106f * u, 14f * u, suave, true, larg - largVel - 6f * u);
            // faixa de baixo: risco, relógio e "4 min · 1,6 km · 12:47"
            float yRisco = qy + 113f * u;
            linha(tela, x - 4f * u, yRisco, fim - 14f * u, yRisco, 1.1f * u, comAlfa(destaque, 0xA0));
            float cx = x + 7f * u, cy = qy + lado - 9f * u, raio = 6f * u;
            tinta.setStyle(Paint.Style.STROKE);
            tinta.setStrokeWidth(1.6f * u);
            tinta.setColor(destaque);
            tela.drawCircle(cx, cy, raio, tinta);
            linha(tela, cx, cy, cx, cy - raio * 0.6f, 1.6f * u, destaque);
            linha(tela, cx, cy, cx + raio * 0.45f, cy + raio * 0.3f, 1.6f * u, destaque);
            texto(tela, resto, x + 19f * u, cy + 4.5f * u, 12.5f * u, suave, false, larg - 34f * u);
        }
    }
}
