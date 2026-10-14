package org.kirito.gthud;

import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;

import java.util.ArrayList;

/**
 * O ouvido do Umbra: o reconhecimento de voz do Android (o do Google), uma escuta por vez.
 *
 * O Python chama ouvir() e confere os campos (como em Fala.java, nada de callback para o
 * Python): estado, texto (as alternativas do que foi dito, uma por linha, da mais provável
 * para a menos), parcial (o que já deu para entender enquanto a pessoa fala) e nivel (o
 * volume da voz de quem fala, de 0 a 1, para o rosto reagir).
 *
 * O SpeechRecognizer só funciona na thread principal do Android: tudo passa pelo Handler.
 *
 * Um reconhecedor NOVO a cada escuta (o anterior é destruído): reaproveitar o mesmo por muitas
 * escutas seguidas (a escuta do nome com a moto parada) fazia ele "emperrar" no Galaxy S23 Ultra,
 * devolvendo erro ou nada, e o Umbra não voltava a ouvir o nome (relato do dono, 14/10/2026).
 */
public class Escuta {
    public static final int PARADA = 0, OUVINDO = 1, ENTENDEU = 2, NADA = 3, SEM_RECONHECIMENTO = -1;
    public static volatile int estado = PARADA;
    public static volatile String texto = "";
    public static volatile String parcial = "";
    public static volatile float nivel = 0f;
    public static volatile int erro = 0;        // o código de erro do Android da última escuta (0 = nenhum)
    private static volatile int sessao = 0;     // muda a cada ouvir()/parar(): resposta de escuta velha é ignorada

    private static SpeechRecognizer rec;
    private static Context ctx;
    private static final Handler principal = new Handler(Looper.getMainLooper());

    public static boolean disponivel(Context c) {
        try {
            return SpeechRecognizer.isRecognitionAvailable(c.getApplicationContext());
        } catch (Exception e) {
            return false;
        }
    }

    /** Começa uma escuta. silencioMs: quanto silêncio depois da fala encerra a escuta. offline:
     * prefere o reconhecimento no próprio celular (mais rápido, sem internet, sem limite de pedidos). */
    public static void ouvir(Context c, final int silencioMs, final boolean offline) {
        ctx = c.getApplicationContext();
        final int minha = ++sessao;
        estado = OUVINDO;
        texto = "";
        parcial = "";
        erro = 0;
        nivel = 0f;
        principal.post(new Runnable() {
            @Override
            public void run() {
                if (minha != sessao) {
                    return;
                }
                try {
                    if (rec != null) {
                        try {
                            rec.destroy();
                        } catch (Exception e) {
                            // nada: vem um novo logo abaixo
                        }
                        rec = null;
                    }
                    rec = SpeechRecognizer.createSpeechRecognizer(ctx);
                    rec.setRecognitionListener(new Ouvinte(minha));
                    Intent i = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
                    i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
                    i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR");
                    i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "pt-BR");
                    i.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
                    i.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 5);
                    i.putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, ctx.getPackageName());
                    i.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, (long) silencioMs);
                    i.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, (long) silencioMs);
                    if (offline) {
                        i.putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true);
                    }
                    rec.startListening(i);
                } catch (Exception e) {
                    if (minha == sessao) {
                        erro = -2;
                        estado = SEM_RECONHECIMENTO;
                    }
                }
            }
        });
    }

    /** Para a escuta em andamento (o que ela ainda entregar é ignorado). */
    public static void parar() {
        sessao++;
        estado = PARADA;
        nivel = 0f;
        principal.post(new Runnable() {
            @Override
            public void run() {
                try {
                    if (rec != null) {
                        rec.cancel();
                    }
                } catch (Exception e) {
                    // nada
                }
            }
        });
    }

    /** Solta o reconhecedor (app fechando). */
    public static void desligar() {
        sessao++;
        estado = PARADA;
        principal.post(new Runnable() {
            @Override
            public void run() {
                try {
                    if (rec != null) {
                        rec.destroy();
                    }
                } catch (Exception e) {
                    // nada
                }
                rec = null;
            }
        });
    }

    private static class Ouvinte implements RecognitionListener {
        private final int minha;

        Ouvinte(int minha) {
            this.minha = minha;
        }

        private boolean velha() {
            return minha != sessao;
        }

        @Override
        public void onReadyForSpeech(Bundle b) {
        }

        @Override
        public void onBeginningOfSpeech() {
        }

        @Override
        public void onRmsChanged(float db) {
            if (!velha()) {
                // o Android dá uns -2 dB em silêncio e uns 10 dB numa fala normal
                nivel = Math.max(0f, Math.min(1f, (db + 2f) / 12f));
            }
        }

        @Override
        public void onBufferReceived(byte[] buffer) {
        }

        @Override
        public void onEndOfSpeech() {
            if (!velha()) {
                nivel = 0f;
            }
        }

        @Override
        public void onError(int codigo) {
            if (velha()) {
                return;
            }
            erro = codigo;
            nivel = 0f;
            estado = NADA;
        }

        @Override
        public void onResults(Bundle b) {
            if (velha()) {
                return;
            }
            ArrayList<String> lista = b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
            StringBuilder sb = new StringBuilder();
            if (lista != null) {
                for (String s : lista) {
                    if (s != null && s.length() > 0) {
                        if (sb.length() > 0) {
                            sb.append('\n');
                        }
                        sb.append(s);
                    }
                }
            }
            texto = sb.toString();
            nivel = 0f;
            estado = texto.length() > 0 ? ENTENDEU : NADA;
        }

        @Override
        public void onPartialResults(Bundle b) {
            if (velha()) {
                return;
            }
            ArrayList<String> lista = b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
            if (lista != null && !lista.isEmpty() && lista.get(0) != null) {
                parcial = lista.get(0);
            }
        }

        @Override
        public void onEvent(int tipo, Bundle b) {
        }
    }
}
