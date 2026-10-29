package com.adrina.kopilka;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.telephony.SmsMessage;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Копилка v1.3 — фоновый приём смсок.
 *
 * Зарегистрирован в манифесте: срабатывает при КАЖДОЙ новой смске, даже
 * когда приложение закрыто. Порядок работы:
 *  1) разбирает pdus из SMS_RECEIVED, склеивает части длинных смсок;
 *  2) кладёт смску в очередь (SharedPreferences, JSON, max 50, с дедупом);
 *  3) показывает уведомление «🐷 Копилка — новая смска»;
 *  4) «будит» приложение явным broadcast'ом ACTION_SMS_ARRIVED —
 *     MainActivity забирает очередь и отдаёт её в WebView
 *     (KOPILKA_ANDROID_SMS): там журнал «💬 Смски», разбор сумм и
 *     авто-добавление поступлений в доход.
 *
 * Разрешения RECEIVE_SMS/READ_SMS запрашиваются из самого приложения
 * (кнопка «✅ Разрешить чтение смсок» в блоке «💬 Смски»); без них
 * система не доставляет SMS_RECEIVED — приём просто не срабатывает.
 */
public class SmsReceiver extends BroadcastReceiver {

    public static final String ACTION_SMS_ARRIVED = "com.adrina.kopilka.SMS_ARRIVED";
    static final String SMS_PREFS = "kopilka_sms_v1";
    static final String SMS_QUEUE = "queue";
    static final String SMS_CHANNEL = "kopilka_sms";
    private static final int MAX_QUEUE = 50;

    @Override
    public void onReceive(Context context, Intent intent) {
        try {
            if (intent == null || intent.getExtras() == null) return;
            String action = intent.getAction();
            if (action == null
                    || !action.equals(android.provider.Telephony.Sms.Intents.SMS_RECEIVED_ACTION)) {
                return;
            }

            String format = intent.getStringExtra("format");
            Object[] pdus = (Object[]) intent.getExtras().get("pdus");
            if (pdus == null || pdus.length == 0) return;

            StringBuilder body = new StringBuilder();
            String from = null;
            long ts = 0;
            for (Object pdu : pdus) {
                if (!(pdu instanceof byte[])) continue;
                SmsMessage m = (format != null && !format.isEmpty())
                        ? SmsMessage.createFromPdu((byte[]) pdu, format)
                        : SmsMessage.createFromPdu((byte[]) pdu);
                if (m == null) continue;
                if (from == null || from.isEmpty()) from = m.getOriginatingAddress();
                String part = m.getMessageBody();
                if (part != null) body.append(part);
                long t = m.getTimestampMillis();
                if (t > ts) ts = t;
            }
            if (from == null || from.isEmpty() || body.length() == 0) return;
            if (ts <= 0) ts = System.currentTimeMillis();

            int notifId = saveToQueue(context, from, body.toString(), ts);
            if (notifId < 0) return;   /* дубль — уже обрабатывали */
            notifySms(context, notifId, from, body.toString());

            /* приложение живо? — оно тут же заберёт очередь и покажет смску в журнале */
            Intent ping = new Intent(ACTION_SMS_ARRIVED);
            ping.setPackage(context.getPackageName());
            context.sendBroadcast(ping);
        } catch (Exception ignored) {
            /* фоновая работа не должна ничего ронять */
        }
    }

    /* ==================== ОЧЕРЕДЬ ==================== */

    /** JSON-массив [{id, from, body, ts}] в SharedPreferences; FIFO, max 50. */
    static synchronized JSONArray readQueue(Context ctx) {
        try {
            SharedPreferences p = ctx.getSharedPreferences(SMS_PREFS, Context.MODE_PRIVATE);
            return new JSONArray(p.getString(SMS_QUEUE, "[]"));
        } catch (Exception e) {
            return new JSONArray();
        }
    }

    static synchronized void writeQueue(Context ctx, JSONArray arr) {
        SharedPreferences p = ctx.getSharedPreferences(SMS_PREFS, Context.MODE_PRIVATE);
        p.edit().putString(SMS_QUEUE, arr.toString()).apply();
    }

    /**
     * Убрать из очереди уже доставленные смски (по id). Вызывается из
     * MainActivity после успешной доставки в WebView. Под тем же локом,
     * что и saveToQueue — новые смски не потеряются.
     */
    static synchronized void removeFromQueue(Context ctx, int[] deliveredIds) {
        if (deliveredIds == null || deliveredIds.length == 0) return;
        JSONArray arr = readQueue(ctx);
        JSONArray out = new JSONArray();
        for (int i = 0; i < arr.length(); i++) {
            JSONObject o = arr.optJSONObject(i);
            int id = (o == null) ? -1 : o.optInt("id", -1);
            boolean delivered = false;
            for (int d : deliveredIds) if (d == id) { delivered = true; break; }
            if (!delivered) out.put(arr.opt(i));
        }
        writeQueue(ctx, out);
    }

    /** Сохранить смску; вернёт id (он же id уведомления) или -1, если дубль. */
    private static synchronized int saveToQueue(Context ctx, String from, String body, long ts) {
        JSONArray arr = readQueue(ctx);
        /* дедуп: та же смска может прийти повторным broadcast'ом */
        for (int i = 0; i < arr.length(); i++) {
            JSONObject o = arr.optJSONObject(i);
            if (o == null) continue;
            if (from.equals(o.optString("from")) && body.equals(o.optString("body"))
                    && Math.abs(ts - o.optLong("ts")) < 5000) {
                return -1;
            }
        }
        int id = (int) ((ts / 1000) % 1000000000L);
        while (idExists(arr, id)) id++;
        JSONObject item = new JSONObject();
        try {
            item.put("id", id);
            item.put("from", from);
            item.put("body", body);
            item.put("ts", ts);
        } catch (Exception ignored) { }
        JSONArray out = new JSONArray();
        out.put(item);
        for (int i = 0; i < arr.length() && out.length() < MAX_QUEUE; i++) out.put(arr.opt(i));
        writeQueue(ctx, out);
        return id;
    }

    private static boolean idExists(JSONArray arr, int id) {
        for (int i = 0; i < arr.length(); i++) {
            JSONObject o = arr.optJSONObject(i);
            if (o != null && o.optInt("id", -1) == id) return true;
        }
        return false;
    }

    /* ==================== УВЕДОМЛЕНИЕ ==================== */

    private static void notifySms(Context ctx, int id, String from, String body) {
        try {
            NotificationManager nm =
                    (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null || !nm.areNotificationsEnabled()) return;
            if (Build.VERSION.SDK_INT >= 26) {
                NotificationChannel ch = new NotificationChannel(SMS_CHANNEL,
                        "Смски", NotificationManager.IMPORTANCE_DEFAULT);
                ch.setDescription("Каждая новая смска для Копилки");
                nm.createNotificationChannel(ch);
            }
            Notification.Builder b = (Build.VERSION.SDK_INT >= 26)
                    ? new Notification.Builder(ctx, SMS_CHANNEL)
                    : new Notification.Builder(ctx);
            String text = from + ": " + body;
            if (text.length() > 400) text = text.substring(0, 400) + "…";
            b.setSmallIcon(R.drawable.ic_launcher)
             .setContentTitle("🐷 Копилка — новая смска")
             .setContentText(text)
             .setStyle(new Notification.BigTextStyle().bigText(text))
             .setAutoCancel(true)
             .setContentIntent(PendingIntent.getActivity(ctx, id,
                     new Intent(ctx, MainActivity.class),
                     PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
            nm.notify(id, b.build());
        } catch (Exception ignored) { }
    }
}
