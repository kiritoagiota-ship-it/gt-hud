package org.kirito.gthud;

import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.content.Context;
import android.os.Build;

import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.List;

/**
 * Por que o app fechou das últimas vezes, segundo o próprio Android (Android 11 ou mais novo).
 *
 * Uma queda dentro da placa de vídeo ou de outra biblioteca nativa não passa pelo Python nem
 * pelo Java: nada no app vê. O Android, porém, guarda o motivo de cada saída e, para uma queda
 * nativa, o laudo (o "tombstone": o sinal, a biblioteca e a função onde quebrou). Aqui o app lê
 * isso na abertura seguinte; diagnostico.py anota no registro que o dono manda pelos Ajustes.
 */
public class Saidas {
    /**
     * As últimas saídas do app, mais nova primeiro, uma por linha:
     * hora_ms|motivo|status|processo|descrição. O laudo da saída mais nova que tiver um vai
     * para caminhoLaudo (o número da linha dela vem na primeira linha: "laudo=N", -1 se nenhum).
     */
    public static String ultimas(Context ctx, int quantas, String caminhoLaudo) {
        if (Build.VERSION.SDK_INT < 30) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        int linhaLaudo = -1;
        try {
            ActivityManager am = (ActivityManager) ctx.getSystemService(Context.ACTIVITY_SERVICE);
            List<ApplicationExitInfo> lista = am.getHistoricalProcessExitReasons(ctx.getPackageName(), 0, quantas);
            for (int n = 0; n < lista.size(); n++) {
                ApplicationExitInfo i = lista.get(n);
                String desc = i.getDescription() == null ? "" : i.getDescription().replace('\n', ' ').replace('|', '/');
                sb.append(i.getTimestamp()).append('|').append(i.getReason()).append('|').append(i.getStatus())
                        .append('|').append(i.getProcessName()).append('|').append(desc).append('\n');
                if (linhaLaudo < 0) {
                    try {
                        InputStream in = i.getTraceInputStream();
                        if (in != null) {
                            FileOutputStream out = new FileOutputStream(caminhoLaudo);
                            byte[] buf = new byte[65536];
                            int lidos, total = 0;
                            while ((lidos = in.read(buf)) > 0 && total < 8 * 1024 * 1024) {
                                out.write(buf, 0, lidos);
                                total += lidos;
                            }
                            out.close();
                            in.close();
                            linhaLaudo = n;
                        }
                    } catch (Throwable ignorado) {
                        // sem laudo: segue só com o motivo
                    }
                }
            }
        } catch (Throwable e) {
            sb.append("erro|").append(e.toString().replace('\n', ' ')).append('\n');
        }
        return "laudo=" + linhaLaudo + "\n" + sb.toString();
    }
}
