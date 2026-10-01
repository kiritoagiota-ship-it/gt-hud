package org.kirito.gthud;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioTrack;
import android.os.Build;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;

import java.io.File;
import java.io.FileInputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Voz do assistente pelo motor de voz do celular (o do Google, se tiver):
 * a FRASE INTEIRA é falada de uma vez, com entonação natural. (Antes o app
 * emendava pedaços gravados e a fala saía picotada.)
 *
 * Com o "efeito" ligado, a frase é sintetizada num arquivo, passa por um
 * tratamento estilo assistente de IA (grave limpo, presença, sala pequena,
 * chorus leve, compressão) e é tocada com AudioTrack. A música do celular
 * abaixa enquanto fala (foco de áudio de navegação).
 *
 * O Python só chama falar() e confere "ocupada"; nada de callback para o
 * Python (ver Localizacao.java).
 */
public class Fala {
    public static volatile int estado = 0;            // 0 iniciando, 1 pronta, -1 sem voz
    public static volatile boolean ocupada = false;
    public static volatile String nomesVozes = "";    // separados por \n
    public static volatile int vozAtual = -1;
    // voz masculina automática: o Android não diz o gênero da voz, então cada
    // voz pt-BR fala uma frase num arquivo (sem tocar) e a altura da voz (F0)
    // é medida; a mais grave é a masculina. -2 nada feito, -1 medindo, >= 0
    // índice da mais grave. tonsVozes: "índice:Hz" de cada uma (diagnóstico).
    public static volatile int vozGrave = -2;
    public static volatile String tonsVozes = "";
    private static final String FRASE_MEDIDA = "Bom dia, senhor. Em duzentos metros, vire à direita.";
    private static List<Integer> paraMedir;
    private static double[] tons;
    private static int medindo = -1;

    private static Context ctx;
    private static TextToSpeech tts;
    private static final List<Voice> vozes = new ArrayList<>();
    private static float tom = 0.88f;
    private static float ritmo = 0.95f;
    private static boolean efeito = true;
    private static boolean tentouPadrao = false;
    private static int contador = 0;
    private static Object pedidoFoco;
    // fala em andamento: o fim de uma fala antiga (cortada pelo parar()) não
    // pode liberar a fila no meio da fala seguinte
    private static volatile String falaAtual = "";
    private static volatile AudioTrack trilhaAtual;

    public static void iniciar(Context c) {
        if (tts != null) {
            return;
        }
        ctx = c.getApplicationContext();
        criar("com.google.android.tts");
    }

    private static void criar(String pacote) {
        TextToSpeech.OnInitListener ouvinte = new TextToSpeech.OnInitListener() {
            @Override
            public void onInit(int status) {
                aoIniciar(status);
            }
        };
        tts = pacote == null ? new TextToSpeech(ctx, ouvinte) : new TextToSpeech(ctx, ouvinte, pacote);
    }

    private static void aoIniciar(int status) {
        if (status != TextToSpeech.SUCCESS) {
            if (!tentouPadrao) {  // sem o motor do Google: tenta o padrão do celular
                tentouPadrao = true;
                try {
                    tts.shutdown();
                } catch (Exception e) {
                    // nada
                }
                criar(null);
            } else {
                estado = -1;
            }
            return;
        }
        try {
            int idioma = tts.setLanguage(new Locale("pt", "BR"));
            vozes.clear();
            Set<Voice> todas = tts.getVoices();
            if (todas != null) {
                for (Voice v : todas) {
                    Locale l = v.getLocale();
                    if (l == null || !"pt".equals(l.getLanguage())) {
                        continue;
                    }
                    String pais = l.getCountry();
                    if (pais != null && !pais.isEmpty() && !"BR".equals(pais)) {
                        continue;
                    }
                    Set<String> recursos = v.getFeatures();
                    if (recursos != null && recursos.contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED)) {
                        continue;
                    }
                    vozes.add(v);
                }
            }
            Collections.sort(vozes, new Comparator<Voice>() {
                @Override
                public int compare(Voice a, Voice b) {
                    if (a.isNetworkConnectionRequired() != b.isNetworkConnectionRequired()) {
                        return a.isNetworkConnectionRequired() ? 1 : -1;  // as offline primeiro
                    }
                    return a.getName().compareTo(b.getName());
                }
            });
            StringBuilder nomes = new StringBuilder();
            for (Voice v : vozes) {
                if (nomes.length() > 0) {
                    nomes.append('\n');
                }
                nomes.append(v.getName());
                if (v.isNetworkConnectionRequired()) {
                    nomes.append(" (online)");
                }
            }
            nomesVozes = nomes.toString();
            tts.setAudioAttributes(atributos());
            tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                @Override
                public void onStart(String id) {
                }

                @Override
                public void onDone(String id) {
                    if (id.startsWith("medida")) {
                        medirArquivo(id);
                        return;
                    }
                    if (!id.equals(falaAtual)) {
                        new File(ctx.getCacheDir(), id + ".wav").delete();  // fala já cortada
                        return;
                    }
                    if (id.startsWith("efeito")) {
                        tocarComEfeito(id);
                    } else {
                        liberar(id);
                    }
                }

                @Override
                public void onError(String id) {
                    if (id.startsWith("medida")) {
                        proximaMedida();
                        return;
                    }
                    liberar(id);
                }
            });
            boolean semIdioma = idioma == TextToSpeech.LANG_MISSING_DATA
                    || idioma == TextToSpeech.LANG_NOT_SUPPORTED;
            estado = (semIdioma && vozes.isEmpty()) ? -1 : 1;
        } catch (Exception e) {
            estado = -1;
        }
    }

    // --- voz masculina automática ---------------------------------------------------
    public static void acharVozGrave() {
        if (estado != 1 || tts == null || vozes.isEmpty() || vozGrave == -1) {
            return;
        }
        paraMedir = new ArrayList<>();
        for (int i = 0; i < vozes.size() && paraMedir.size() < 10; i++) {
            if (!vozes.get(i).isNetworkConnectionRequired()) {
                paraMedir.add(i);  // só as que funcionam sem internet
            }
        }
        if (paraMedir.isEmpty()) {
            for (int i = 0; i < vozes.size() && i < 6; i++) {
                paraMedir.add(i);
            }
        }
        tons = new double[vozes.size()];
        tonsVozes = "";
        medindo = -1;
        vozGrave = -1;
        proximaMedida();
    }

    private static void proximaMedida() {
        medindo++;
        if (medindo >= paraMedir.size()) {
            int melhor = -2;
            for (int i : paraMedir) {
                if (tons[i] > 0 && (melhor < 0 || tons[i] < tons[melhor])) {
                    melhor = i;
                }
            }
            try {  // volta para a voz que estava
                if (vozAtual >= 0) {
                    tts.setVoice(vozes.get(vozAtual));
                }
            } catch (Exception e) {
                // nada
            }
            vozGrave = melhor;
            return;
        }
        int i = paraMedir.get(medindo);
        try {
            tts.setVoice(vozes.get(i));
            tts.setPitch(1.0f);
            tts.setSpeechRate(1.0f);
            String id = "medida" + i;
            File arquivo = new File(ctx.getCacheDir(), id + ".wav");
            if (tts.synthesizeToFile(FRASE_MEDIDA, new Bundle(), arquivo, id) == TextToSpeech.SUCCESS) {
                return;  // segue em onDone -> medirArquivo
            }
        } catch (Exception e) {
            // essa voz não deu: pula
        }
        proximaMedida();
    }

    private static void medirArquivo(final String id) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                File arquivo = new File(ctx.getCacheDir(), id + ".wav");
                try {
                    int i = Integer.parseInt(id.substring("medida".length()));
                    int[] taxa = new int[1];
                    short[] pcm = lerWav(lerArquivo(arquivo), taxa);
                    if (pcm != null && pcm.length > 0) {
                        tons[i] = alturaDaVoz(pcm, taxa[0]);
                        tonsVozes += i + ":" + Math.round(tons[i]) + " ";
                    }
                } catch (Exception e) {
                    // sem medida dessa voz
                } finally {
                    arquivo.delete();
                    proximaMedida();
                }
            }
        }).start();
    }

    /** Altura (F0, Hz) mediana da voz, por autocorrelação em janelas de 40 ms.
     *  Voz masculina ~85-155 Hz, feminina ~165-255 Hz. */
    private static double alturaDaVoz(short[] pcm, int taxa) {
        int janela = taxa * 40 / 1000;
        int passo = taxa / 50;
        int lagMin = taxa / 320;
        int lagMax = taxa / 65;
        double maiorRms = 0;
        for (int ini = 0; ini + janela < pcm.length; ini += passo) {
            double e = 0;
            for (int k = ini; k < ini + janela; k++) {
                e += (double) pcm[k] * pcm[k];
            }
            maiorRms = Math.max(maiorRms, Math.sqrt(e / janela));
        }
        List<Double> f0 = new ArrayList<>();
        double[] r = new double[lagMax + 1];
        for (int ini = 0; ini + janela + lagMax < pcm.length; ini += passo) {
            double e0 = 0;
            for (int k = ini; k < ini + janela; k++) {
                e0 += (double) pcm[k] * pcm[k];
            }
            if (Math.sqrt(e0 / janela) < maiorRms * 0.25) {
                continue;  // silêncio ou consoante fraca
            }
            double maior = 0;
            for (int lag = lagMin; lag <= lagMax; lag++) {
                double soma = 0, e1 = 0;
                for (int k = ini; k < ini + janela; k++) {
                    soma += (double) pcm[k] * pcm[k + lag];
                    e1 += (double) pcm[k + lag] * pcm[k + lag];
                }
                r[lag] = soma / Math.sqrt(e0 * e1 + 1e-9);
                maior = Math.max(maior, r[lag]);
            }
            if (maior < 0.6) {
                continue;  // trecho sem tom (s, f, x...)
            }
            // o MENOR atraso perto do máximo: evita confundir com meia altura
            for (int lag = lagMin + 1; lag < lagMax; lag++) {
                if (r[lag] >= maior * 0.9 && r[lag] >= r[lag - 1] && r[lag] >= r[lag + 1]) {
                    f0.add(taxa / (double) lag);
                    break;
                }
            }
        }
        if (f0.size() < 5) {
            return 0;
        }
        Collections.sort(f0);
        return f0.get(f0.size() / 2);
    }

    public static void escolherVoz(int indice) {
        if (tts != null && indice >= 0 && indice < vozes.size()) {
            try {
                tts.setVoice(vozes.get(indice));
                vozAtual = indice;
            } catch (Exception e) {
                // fica a voz que estava
            }
        }
    }

    public static void ajustar(float novoTom, float novoRitmo, boolean comEfeito) {
        tom = novoTom;
        ritmo = novoRitmo;
        efeito = comEfeito;
    }

    public static boolean falar(String texto) {
        if (estado != 1 || tts == null) {
            return false;
        }
        contador++;
        String id = (efeito ? "efeito" : "direto") + contador;
        falaAtual = id;
        ocupada = true;
        try {
            tts.setPitch(tom);
            tts.setSpeechRate(ritmo);
            Bundle params = new Bundle();
            if (efeito) {
                File arquivo = new File(ctx.getCacheDir(), id + ".wav");
                if (tts.synthesizeToFile(texto, params, arquivo, id) == TextToSpeech.SUCCESS) {
                    return true;
                }
            } else {
                pegarFoco();
                if (tts.speak(texto, TextToSpeech.QUEUE_FLUSH, params, id) == TextToSpeech.SUCCESS) {
                    return true;
                }
            }
        } catch (Exception e) {
            // cai no liberar abaixo
        }
        liberar(id);
        return false;
    }

    /** Corta a fala atual (inclusive a que já está tocando com efeito). */
    public static void parar() {
        falaAtual = "";
        try {
            if (tts != null) {
                tts.stop();
            }
        } catch (Exception e) {
            // nada
        }
        AudioTrack trilha = trilhaAtual;
        if (trilha != null) {
            try {
                trilha.pause();
                trilha.flush();
            } catch (Exception e) {
                // já tinha terminado
            }
        }
        soltarFoco();
        ocupada = false;
    }

    // --- tratamento estilo assistente de IA -------------------------------------
    private static void tocarComEfeito(final String id) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                File arquivo = new File(ctx.getCacheDir(), id + ".wav");
                try {
                    int[] taxa = new int[1];
                    short[] pcm = lerWav(lerArquivo(arquivo), taxa);
                    if (pcm != null && pcm.length > 0 && id.equals(falaAtual)) {
                        tocar(processar(pcm, taxa[0]), taxa[0], id);
                    }
                } catch (Exception e) {
                    // sem efeito dessa vez: segue a vida
                } finally {
                    arquivo.delete();
                    liberar(id);
                }
            }
        }).start();
    }

    private static byte[] lerArquivo(File f) throws Exception {
        byte[] b = new byte[(int) f.length()];
        FileInputStream in = new FileInputStream(f);
        try {
            int lido = 0;
            while (lido < b.length) {
                int n = in.read(b, lido, b.length - lido);
                if (n < 0) {
                    break;
                }
                lido += n;
            }
        } finally {
            in.close();
        }
        return b;
    }

    private static int le16(byte[] b, int i) {
        return (b[i] & 0xff) | ((b[i + 1] & 0xff) << 8);
    }

    private static int le32(byte[] b, int i) {
        return le16(b, i) | (le16(b, i + 2) << 16);
    }

    private static short[] lerWav(byte[] b, int[] taxaSaida) {
        int i = 12;
        int taxa = 22050;
        int canais = 1;
        int bits = 16;
        int inicio = -1;
        int tamanho = 0;
        while (i + 8 <= b.length) {
            String bloco = new String(b, i, 4);
            int t = le32(b, i + 4);
            if (bloco.equals("fmt ")) {
                canais = Math.max(1, le16(b, i + 10));
                taxa = le32(b, i + 12);
                bits = le16(b, i + 22);
            } else if (bloco.equals("data")) {
                inicio = i + 8;
                tamanho = (t <= 0 || t > b.length - inicio) ? b.length - inicio : t;
                break;
            }
            if (t < 0) {
                break;
            }
            i += 8 + t + (t & 1);
        }
        if (inicio < 0 || bits != 16) {
            return null;
        }
        int n = tamanho / 2 / canais;
        short[] s = new short[n];
        for (int k = 0; k < n; k++) {
            int o = inicio + k * 2 * canais;
            s[k] = (short) ((b[o] & 0xff) | (b[o + 1] << 8));
        }
        taxaSaida[0] = taxa;
        return s;
    }

    /** Filtro biquad (receitas do "Audio EQ Cookbook"): a = {b0, b1, b2, a1, a2}. */
    private static void biquad(float[] x, double[] c) {
        double x1 = 0, x2 = 0, y1 = 0, y2 = 0;
        for (int k = 0; k < x.length; k++) {
            double x0 = x[k];
            double y0 = c[0] * x0 + c[1] * x1 + c[2] * x2 - c[3] * y1 - c[4] * y2;
            x2 = x1;
            x1 = x0;
            y2 = y1;
            y1 = y0;
            x[k] = (float) y0;
        }
    }

    private static double[] normalizar(double b0, double b1, double b2, double a0, double a1, double a2) {
        return new double[]{b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0};
    }

    private static double[] passaAlta(double f, double taxa, double q) {
        double w = 2 * Math.PI * f / taxa, al = Math.sin(w) / (2 * q), cs = Math.cos(w);
        return normalizar((1 + cs) / 2, -(1 + cs), (1 + cs) / 2, 1 + al, -2 * cs, 1 - al);
    }

    private static double[] passaBaixa(double f, double taxa, double q) {
        double w = 2 * Math.PI * f / taxa, al = Math.sin(w) / (2 * q), cs = Math.cos(w);
        return normalizar((1 - cs) / 2, 1 - cs, (1 - cs) / 2, 1 + al, -2 * cs, 1 - al);
    }

    private static double[] pico(double f, double taxa, double q, double db) {
        double a = Math.pow(10, db / 40), w = 2 * Math.PI * f / taxa;
        double al = Math.sin(w) / (2 * q), cs = Math.cos(w);
        return normalizar(1 + al * a, -2 * cs, 1 - al * a, 1 + al / a, -2 * cs, 1 - al / a);
    }

    private static double[] prateleiraAlta(double f, double taxa, double db) {
        double a = Math.pow(10, db / 40), w = 2 * Math.PI * f / taxa, cs = Math.cos(w);
        double al = Math.sin(w) / 2 * Math.sqrt(2), r = 2 * Math.sqrt(a) * al;
        return normalizar(a * ((a + 1) + (a - 1) * cs + r), -2 * a * ((a - 1) + (a + 1) * cs),
                a * ((a + 1) + (a - 1) * cs - r), (a + 1) - (a - 1) * cs + r,
                2 * ((a - 1) - (a + 1) * cs), (a + 1) - (a - 1) * cs - r);
    }

    private static float[] processar(short[] s, int taxa) {
        int n = s.length;
        float[] x = new float[n];
        for (int k = 0; k < n; k++) {
            x[k] = s[k] / 32768f;
        }
        biquad(x, passaAlta(140, taxa, 0.707));                 // grave que o celular não toca
        biquad(x, pico(2800, taxa, 1.0, 5.0));                  // presença: clareza no vento
        biquad(x, prateleiraAlta(6000, taxa, 2.5));             // brilho leve
        biquad(x, passaBaixa(Math.min(10500, taxa * 0.45), taxa, 0.707));
        float[] y = x.clone();                                  // sala pequena, discreta
        int[] ms = {11, 23, 37};
        float[] ganho = {0.07f, 0.045f, 0.025f};
        for (int j = 0; j < ms.length; j++) {
            int d = taxa * ms[j] / 1000;
            for (int k = d; k < n; k++) {
                y[k] += ganho[j] * x[k - d];
            }
        }
        float[] z = y.clone();                                  // assinatura "digital" leve
        for (int k = 0; k < n; k++) {
            double pos = k - (0.006 + 0.0015 * Math.sin(2 * Math.PI * 0.8 * k / taxa)) * taxa;
            if (pos >= 0) {
                int p0 = (int) pos;
                double fr = pos - p0;
                z[k] += 0.035f * (float) (y[p0] * (1 - fr) + y[Math.min(p0 + 1, n - 1)] * fr);
            }
        }
        float maior = 1e-6f;
        for (float v : z) {
            maior = Math.max(maior, Math.abs(v));
        }
        double t = Math.tanh(1.6);
        for (int k = 0; k < n; k++) {                           // compressão suave
            z[k] = (float) (Math.tanh(1.6 * z[k] / maior) / t * 0.95);
        }
        return z;
    }

    private static void tocar(float[] x, int taxa, String id) throws InterruptedException {
        int silencio = taxa / 10;  // 0,1 s antes: o fone Bluetooth "come" o começo
        short[] pcm = new short[x.length + silencio];
        for (int k = 0; k < x.length; k++) {
            pcm[silencio + k] = (short) Math.max(-32767, Math.min(32767, x[k] * 32767));
        }
        AudioTrack trilha = new AudioTrack.Builder()
                .setAudioAttributes(atributos())
                .setAudioFormat(new AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(taxa)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build())
                .setBufferSizeInBytes(pcm.length * 2)
                .setTransferMode(AudioTrack.MODE_STATIC)
                .build();
        trilhaAtual = trilha;
        try {
            trilha.write(pcm, 0, pcm.length);
            if (!id.equals(falaAtual)) {
                return;  // cortada enquanto processava
            }
            pegarFoco();
            trilha.play();
            // espera tocar, acordando a cada 50 ms para ver se foi cortada
            long fim = System.currentTimeMillis() + pcm.length * 1000L / taxa + 150;
            while (System.currentTimeMillis() < fim && id.equals(falaAtual)) {
                Thread.sleep(50);
            }
            trilha.stop();
        } finally {
            trilhaAtual = null;
            trilha.release();
        }
    }

    // --- foco de áudio: a música abaixa enquanto o assistente fala ------------------
    private static AudioAttributes atributos() {
        return new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build();
    }

    private static void pegarFoco() {
        try {
            AudioManager am = (AudioManager) ctx.getSystemService(Context.AUDIO_SERVICE);
            if (Build.VERSION.SDK_INT >= 26) {
                AudioFocusRequest pedido = new AudioFocusRequest.Builder(
                        AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
                        .setAudioAttributes(atributos()).build();
                pedidoFoco = pedido;
                am.requestAudioFocus(pedido);
            } else {
                am.requestAudioFocus(null, AudioManager.STREAM_MUSIC,
                        AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK);
            }
        } catch (Exception e) {
            // sem foco: fala por cima mesmo
        }
    }

    private static void soltarFoco() {
        try {
            AudioManager am = (AudioManager) ctx.getSystemService(Context.AUDIO_SERVICE);
            if (Build.VERSION.SDK_INT >= 26 && pedidoFoco != null) {
                am.abandonAudioFocusRequest((AudioFocusRequest) pedidoFoco);
            } else {
                am.abandonAudioFocus(null);
            }
        } catch (Exception e) {
            // nada
        }
    }

    /** Fim da fala `id`: só libera se ela ainda for a atual. */
    private static void liberar(String id) {
        if (!id.equals(falaAtual)) {
            return;
        }
        falaAtual = "";
        soltarFoco();
        ocupada = false;
    }
}
