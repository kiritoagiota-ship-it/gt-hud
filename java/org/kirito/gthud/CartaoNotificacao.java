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
                                  int segmentos, int acesos) {
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

        if (!grande) {
            // ---- a faixa: [barrinhas]  VALOR  rótulo ................ LADO
            float x = margem;
            if (segmentos > 0) {
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

        texto.setColor(forte);
        texto.setTextSize(33f * u);
        if (valor != null) {
            tela.drawText(valor, margem, 63f * u, texto);
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

    private static void desenharBarrinhas(Canvas tela, Paint tinta, float x, float y, float cada, float alto,
                                          float vao, float inclina, int segmentos, int acesos,
                                          int borda, int aura, int apagado, float u) {
        for (int n = 0; n < segmentos; n++) {
            Path b = barrinha(x + n * (cada + vao), y, cada, alto, inclina);
            if (n < acesos) {
                // acesas: do azul da borda (a primeira) ao roxo da aura (a última), com brilho em volta
                int corDela = misturar(borda, aura, segmentos > 1 ? n / (float) (segmentos - 1) : 0f);
                tinta.setStyle(Paint.Style.STROKE);
                tinta.setStrokeWidth(3.2f * u);
                tinta.setColor(comAlfa(corDela, 0x55));
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
