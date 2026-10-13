package org.kirito.gthud;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.text.TextPaint;
import android.text.TextUtils;
import android.util.DisplayMetrics;

/**
 * O "cartão" da notificação do GT-HUD, desenhado inteiro como imagem (pedido do
 * dono, 12/10/2026: uma notificação "bem a nossa cara", fora do comum, que também
 * apareça com a tela bloqueada). Mesmo traço das janelas do app: moldura de cantos
 * cortados com brilho, fundo em degradê e as barrinhas acesas.
 *
 * Duas alturas: a faixa (notificação recolhida, e a da tela bloqueada) e o cartão
 * (notificação aberta). O serviço (ServicoNavegacao) põe a imagem num layout de um
 * ImageView só (res/layout/gthud_notificacao.xml).
 *
 * A mesma conta está em ferramentas/previa_notificacao.py, para ver no PC.
 */
public class CartaoNotificacao {

    private static int cor(boolean claro, boolean monarca, String noClaro, String noEscuro, String noMonarca) {
        return Color.parseColor(claro ? noClaro : (monarca ? noMonarca : noEscuro));
    }

    private static int misturar(int a, int b, float f) {
        f = Math.max(0f, Math.min(1f, f));
        return Color.argb(255,
                Math.round(Color.red(a) + (Color.red(b) - Color.red(a)) * f),
                Math.round(Color.green(a) + (Color.green(b) - Color.green(a)) * f),
                Math.round(Color.blue(a) + (Color.blue(b) - Color.blue(a)) * f));
    }

    private static int comAlfa(int corBase, int alfa) {
        return (corBase & 0x00FFFFFF) | (alfa << 24);
    }

    /** Polígono com os cantos de cima-esquerda e de baixo-direita cortados. */
    private static Path moldura(float x0, float y0, float x1, float y1, float c) {
        Path p = new Path();
        p.moveTo(x0 + c, y0);
        p.lineTo(x1, y0);
        p.lineTo(x1, y1 - c);
        p.lineTo(x1 - c, y1);
        p.lineTo(x0, y1);
        p.lineTo(x0, y0 + c);
        p.close();
        return p;
    }

    /** Uma barrinha inclinada (paralelogramo). */
    private static Path barrinha(float x, float y, float w, float h, float inclina) {
        Path p = new Path();
        p.moveTo(x + inclina, y);
        p.lineTo(x + w + inclina, y);
        p.lineTo(x + w, y + h);
        p.lineTo(x, y + h);
        p.close();
        return p;
    }

    public static Bitmap desenhar(Context c, boolean grande, boolean claro, boolean monarca,
                                  String rotulo, String valor, String lado, String sub,
                                  int segmentos, int acesos, String seta) {
        DisplayMetrics dm = c.getResources().getDisplayMetrics();
        float u = Math.min(dm.density, 2.5f);     // pixels por "dp" do desenho (teto: a imagem não pode pesar)
        float larguraDp = Math.max(240f, Math.min(dm.widthPixels / dm.density - 32f, 420f));
        int w = Math.round(larguraDp * u);
        int h = Math.round((grande ? 124f : 46f) * u);
        Bitmap imagem = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
        Canvas tela = new Canvas(imagem);

        int fundoCima = cor(claro, monarca, "#FFFFFF", "#0C1826", "#17133F");
        int fundoBaixo = cor(claro, monarca, "#EAF1F5", "#05090F", "#07061A");
        int borda = cor(claro, monarca, "#00788F", "#19E3FF", "#5AA0FF");
        int aura = cor(claro, monarca, "#00788F", "#19E3FF", "#9B5CFF");
        int forte = cor(claro, monarca, "#0A1A24", "#F2FBFF", "#EEF0FF");
        int suave = cor(claro, monarca, "#3F6272", "#A9DCEA", "#A7A2F0");
        int apagado = cor(claro, monarca, "#C9D8DE", "#0F2A36", "#231F58");

        Paint tinta = new Paint(Paint.ANTI_ALIAS_FLAG);
        float m = 3f * u;                         // folga para o brilho da moldura
        float canto = (grande ? 13f : 9f) * u;
        Path contorno = moldura(m, m, w - m, h - m, canto);

        // fundo em degradê
        tinta.setStyle(Paint.Style.FILL);
        tinta.setShader(new LinearGradient(0, m, 0, h - m, fundoCima, fundoBaixo, Shader.TileMode.CLAMP));
        tela.drawPath(contorno, tinta);
        tinta.setShader(null);

        // linhas finas de painel no fundo (só dentro da moldura)
        tela.save();
        tela.clipPath(contorno);
        tinta.setStyle(Paint.Style.STROKE);
        tinta.setStrokeWidth(Math.max(1f, 0.5f * u));
        tinta.setColor(comAlfa(borda, claro ? 0x10 : 0x17));
        for (float yy = m + 5f * u; yy < h - m; yy += 5f * u) {
            tela.drawLine(m, yy, w - m, yy, tinta);
        }
        tela.restore();

        // a aura por trás da borda, a borda e os dois cantos cortados marcados
        tinta.setStyle(Paint.Style.STROKE);
        tinta.setStrokeJoin(Paint.Join.ROUND);
        tinta.setStrokeWidth(5f * u);
        tinta.setColor(comAlfa(aura, claro ? 0x22 : 0x48));
        tela.drawPath(contorno, tinta);
        tinta.setStrokeWidth(1.3f * u);
        tinta.setColor(borda);
        tela.drawPath(contorno, tinta);
        tinta.setStrokeWidth(2.8f * u);
        tinta.setStrokeCap(Paint.Cap.SQUARE);
        float e = canto * 0.9f;
        Path marcas = new Path();
        marcas.moveTo(m, m + canto + e);
        marcas.lineTo(m, m + canto);
        marcas.lineTo(m + canto, m);
        marcas.lineTo(m + canto + e, m);
        marcas.moveTo(w - m, h - m - canto - e);
        marcas.lineTo(w - m, h - m - canto);
        marcas.lineTo(w - m - canto, h - m);
        marcas.lineTo(w - m - canto - e, h - m);
        tela.drawPath(marcas, tinta);
        tinta.setStrokeCap(Paint.Cap.BUTT);

        TextPaint texto = new TextPaint(Paint.ANTI_ALIAS_FLAG);
        texto.setTypeface(Typeface.create(Typeface.DEFAULT, Typeface.BOLD));
        float margem = 15f * u;
        boolean comSeta = seta != null && seta.length() > 0;
        if (grande) {
            fase++;      // a barrinha da vez alterna o brilho a cada atualização
        }

        if (!grande) {
            // ---- a faixa: [barrinhas]  VALOR  rótulo ................ LADO
            float x = margem;
            if (comSeta) {
                float tam = h - 2f * m - 12f * u;
                desenharSeta(tela, tinta, x, (h - tam) / 2f, tam, seta, borda, aura, u);
                x += tam + 8f * u;
            } else if (segmentos > 0) {
                float alto = h - 2f * m - 16f * u;
                float vao = 3.5f * u;
                float cada = Math.min(12f * u, (w * 0.34f) / segmentos - vao);
                float y = (h - alto) / 2f;
                desenharBarrinhas(tela, tinta, x, y, cada, alto, vao, 4f * u, segmentos, acesos,
                        borda, aura, apagado, u);
                x += segmentos * (cada + vao) + 9f * u;
            }
            float linha = h / 2f;
            texto.setColor(borda);
            texto.setTextSize(16f * u);
            float largLado = lado == null ? 0f : texto.measureText(lado);
            if (lado != null && lado.length() > 0) {
                tela.drawText(lado, w - margem - largLado, linha + 5.8f * u, texto);
            }
            texto.setColor(forte);
            texto.setTextSize(19f * u);
            float limite = w - margem - largLado - 10f * u;
            String v = valor == null ? "" : valor;
            tela.drawText(v, x, linha + 6.8f * u, texto);
            x += texto.measureText(v) + 8f * u;
            if (rotulo != null && x < limite - 30f * u) {
                texto.setTypeface(Typeface.DEFAULT);
                texto.setColor(suave);
                texto.setTextSize(11f * u);
                // (na faixa cabe pouco: só o fim do rótulo, "bateria da moto" ou o nome do destino)
                int corte = rotulo.lastIndexOf('·');
                String curto = (corte >= 0 ? rotulo.substring(corte + 1) : rotulo).trim().toLowerCase();
                CharSequence r = TextUtils.ellipsize(curto, texto, limite - x, TextUtils.TruncateAt.END);
                tela.drawText(r, 0, r.length(), x, linha + 5f * u, texto);
            }
            return imagem;
        }

        // ---- o cartão: rótulo e LADO em cima, VALOR grande, barrinhas largas, frase embaixo
        float d = 3.6f * u;                       // o losango do "Sistema" antes do rótulo
        float cy = 21f * u;
        Path losango = new Path();
        losango.moveTo(margem + d, cy - d);
        losango.lineTo(margem + 2f * d, cy);
        losango.lineTo(margem + d, cy + d);
        losango.lineTo(margem, cy);
        losango.close();
        tinta.setStyle(Paint.Style.FILL);
        tinta.setColor(aura);
        tela.drawPath(losango, tinta);

        texto.setColor(borda);
        texto.setTextSize(15f * u);
        float largLado = lado == null ? 0f : texto.measureText(lado);
        if (lado != null && lado.length() > 0) {
            tela.drawText(lado, w - margem - largLado, cy + 5.2f * u, texto);
        }
        texto.setColor(suave);
        texto.setTextSize(10.5f * u);
        texto.setLetterSpacing(0.12f);
        if (rotulo != null) {
            float x = margem + 2f * d + 7f * u;
            CharSequence r = TextUtils.ellipsize(rotulo, texto, w - margem - largLado - 10f * u - x,
                    TextUtils.TruncateAt.END);
            tela.drawText(r, 0, r.length(), x, cy + 3.7f * u, texto);
        }
        texto.setLetterSpacing(0f);

        float xValor = margem;
        if (comSeta) {
            float tam = 40f * u;
            desenharSeta(tela, tinta, margem, 28f * u, tam, seta, borda, aura, u);
            xValor += tam + 10f * u;
        }
        texto.setColor(forte);
        texto.setTextSize(33f * u);
        if (valor != null) {
            texto.setShadowLayer(9f * u, 0f, 0f, comAlfa(aura, claro ? 0x55 : 0xC8));   // o brilho atrás do número
            tela.drawText(valor, xValor, 63f * u, texto);
            texto.clearShadowLayer();
        }

        if (segmentos > 0) {
            float vao = 4f * u;
            float inclina = 5f * u;
            float cada = (w - 2f * margem - inclina - (segmentos - 1) * vao) / segmentos;
            desenharBarrinhas(tela, tinta, margem, 75f * u, cada, 15f * u, vao, inclina, segmentos, acesos,
                    borda, aura, apagado, u);
        }

        if (sub != null && sub.length() > 0) {
            texto.setTypeface(Typeface.DEFAULT);
            texto.setColor(suave);
            texto.setTextSize(11.5f * u);
            CharSequence s = TextUtils.ellipsize(sub, texto, w - 2f * margem, TextUtils.TruncateAt.END);
            tela.drawText(s, 0, s.length(), margem, h - m - 9f * u, texto);
        }
        return imagem;
    }

    private static int fase = 0;

    /** A seta da próxima manobra (as mesmas ações do app: "direita", "levemente_esquerda",
     *  "retorno", "rotatoria", "chegada"...), num quadrado de lado `tam` a partir de (x0, y0). */
    private static void desenharSeta(Canvas tela, Paint tinta, float x0, float y0, float tam, String acao,
                                     int corSeta, int aura, float u) {
        boolean espelho = acao.endsWith("esquerda");
        float[] pts;          // o caminho, em frações do quadrado (x para a direita, y para baixo)
        float dx, dy;         // para onde a ponta aponta
        if (acao.startsWith("chegada")) {
            tinta.setStyle(Paint.Style.STROKE);
            tinta.setStrokeWidth(tam * 0.10f);
            tinta.setColor(corSeta);
            tela.drawCircle(x0 + tam * 0.5f, y0 + tam * 0.5f, tam * 0.38f, tinta);
            tela.drawCircle(x0 + tam * 0.5f, y0 + tam * 0.5f, tam * 0.20f, tinta);
            tinta.setStyle(Paint.Style.FILL);
            tela.drawCircle(x0 + tam * 0.5f, y0 + tam * 0.5f, tam * 0.07f, tinta);
            return;
        }
        if (acao.startsWith("rotatoria") || acao.startsWith("sair_rotatoria")) {
            tinta.setStyle(Paint.Style.STROKE);
            tinta.setStrokeWidth(tam * 0.11f);
            tinta.setStrokeCap(Paint.Cap.ROUND);
            tinta.setColor(corSeta);
            tela.drawCircle(x0 + tam * 0.46f, y0 + tam * 0.56f, tam * 0.21f, tinta);
            tela.drawLine(x0 + tam * 0.46f, y0 + tam * 0.96f, x0 + tam * 0.46f, y0 + tam * 0.78f, tinta);
            tinta.setStrokeCap(Paint.Cap.BUTT);
            pts = new float[] {0.61f, 0.41f, 0.80f, 0.22f};
            dx = 0.707f;
            dy = -0.707f;
            espelho = false;
        } else if (acao.equals("retorno")) {
            pts = new float[] {0.68f, 0.92f, 0.68f, 0.30f, 0.32f, 0.30f, 0.32f, 0.60f};
            dx = 0f;
            dy = 1f;
        } else if (acao.startsWith("levemente") || acao.startsWith("mantenha") || acao.startsWith("saida")) {
            pts = new float[] {0.36f, 0.92f, 0.36f, 0.52f, 0.68f, 0.20f};
            dx = 0.707f;
            dy = -0.707f;
        } else if (acao.startsWith("acentuada")) {
            pts = new float[] {0.30f, 0.92f, 0.30f, 0.28f, 0.66f, 0.64f};
            dx = 0.707f;
            dy = 0.707f;
        } else if (acao.equals("direita") || acao.equals("esquerda")) {
            pts = new float[] {0.28f, 0.92f, 0.28f, 0.36f, 0.76f, 0.36f};
            dx = 1f;
            dy = 0f;
        } else {             // em frente (e o que não conhecer)
            pts = new float[] {0.5f, 0.92f, 0.5f, 0.24f};
            dx = 0f;
            dy = -1f;
        }
        Path caminho = new Path();
        for (int k = 0; k < pts.length; k += 2) {
            float px = x0 + (espelho ? 1f - pts[k] : pts[k]) * tam;
            float py = y0 + pts[k + 1] * tam;
            if (k == 0) {
                caminho.moveTo(px, py);
            } else {
                caminho.lineTo(px, py);
            }
        }
        if (espelho) {
            dx = -dx;
        }
        float tx = x0 + (espelho ? 1f - pts[pts.length - 2] : pts[pts.length - 2]) * tam;
        float ty = y0 + pts[pts.length - 1] * tam;
        Path ponta = new Path();     // triângulo na ponta, apontando para (dx, dy)
        float comp = tam * 0.20f;
        float meia = tam * 0.15f;
        ponta.moveTo(tx + dx * comp, ty + dy * comp);
        ponta.lineTo(tx - dy * meia, ty + dx * meia);
        ponta.lineTo(tx + dy * meia, ty - dx * meia);
        ponta.close();
        tinta.setStrokeJoin(Paint.Join.ROUND);
        tinta.setStrokeCap(Paint.Cap.ROUND);
        tinta.setStyle(Paint.Style.STROKE);
        tinta.setStrokeWidth(tam * 0.22f);                 // o brilho em volta
        tinta.setColor(comAlfa(aura, 0x50));
        tela.drawPath(caminho, tinta);
        tinta.setStrokeWidth(tam * 0.12f);
        tinta.setColor(corSeta);
        tela.drawPath(caminho, tinta);
        tinta.setStyle(Paint.Style.FILL_AND_STROKE);
        tinta.setStrokeWidth(tam * 0.04f);
        tela.drawPath(ponta, tinta);
        tinta.setStrokeCap(Paint.Cap.BUTT);
        tinta.setStyle(Paint.Style.FILL);
    }

    private static void desenharBarrinhas(Canvas tela, Paint tinta, float x, float y, float cada, float alto,
                                          float vao, float inclina, int segmentos, int acesos,
                                          int borda, int aura, int apagado, float u) {
        for (int n = 0; n < segmentos; n++) {
            Path b = barrinha(x + n * (cada + vao), y, cada, alto, inclina);
            if (n < acesos) {
                // acesas: do azul da borda (a primeira) ao roxo da aura (a última), com brilho em volta
                int corDela = misturar(borda, aura, segmentos > 1 ? n / (float) (segmentos - 1) : 0f);
                boolean daVez = n == acesos - 1 && acesos < segmentos + 1;
                if (daVez) {       // a barrinha da vez: mais clara, com o brilho maior
                    corDela = misturar(corDela, Color.WHITE, fase % 2 == 0 ? 0.30f : 0.52f);
                }
                tinta.setStyle(Paint.Style.STROKE);
                tinta.setStrokeWidth((daVez ? 5.5f : 3.2f) * u);
                tinta.setColor(comAlfa(corDela, daVez ? 0x80 : 0x55));
                tela.drawPath(b, tinta);
                tinta.setStyle(Paint.Style.FILL);
                tinta.setColor(corDela);
                tela.drawPath(b, tinta);
            } else {
                tinta.setStyle(Paint.Style.FILL);
                tinta.setColor(apagado);
                tela.drawPath(b, tinta);
            }
        }
    }
}
