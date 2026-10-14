package org.kirito.gthud;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * Erro do lado Java/Android que fecharia o app (ex.: dentro do reconhecimento de voz): o
 * diagnóstico do Python não vê esses. Aqui o erro é anotado num arquivo (erro_java.txt, na
 * pasta do app) e depois o Android segue como sempre; na próxima abertura, diagnostico.py
 * põe o conteúdo no registro que o dono manda pelos Ajustes.
 */
public class Diario {
    private static boolean instalado = false;

    public static synchronized void instalar(final String caminho) {
        if (instalado) {
            return;
        }
        instalado = true;
        final Thread.UncaughtExceptionHandler anterior = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler(new Thread.UncaughtExceptionHandler() {
            @Override
            public void uncaughtException(Thread t, Throwable e) {
                try {
                    PrintWriter w = new PrintWriter(new FileWriter(caminho, true));
                    w.println(new SimpleDateFormat("HH:mm:ss", Locale.US).format(new Date())
                            + " na thread \"" + t.getName() + "\":");
                    e.printStackTrace(w);
                    w.close();
                } catch (Throwable ignorado) {
                    // nada: o importante é o Android seguir com o erro
                }
                if (anterior != null) {
                    anterior.uncaughtException(t, e);
                }
            }
        });
    }
}
