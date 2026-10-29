package com.adrina.kopilka;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.util.Base64;
import android.view.KeyEvent;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * Копилка для Android — WebView-обёртка над kopilka index.html.
 * Данные — в localStorage (setDomStorageEnabled). Chart.js и все ресурсы
 * в assets — работает офлайн. GitHub-синхронизация — через api.github.com.
 *
 * Мост «Android»:
 *  - downloadFile(name, base64, mime) — сохранение бэкапов/файлов Секретной
 *    папки через системный диалог «Сохранить как» (SAF, без разрешений);
 *  - выбор файлов (<input type=file>) — onShowFileChooser.
 *
 * НОВОЕ в v1.1 — перенос данных из браузера:
 *  - при ПЕРВОМ запуске и после КАЖДОГО ОБНОВЛЕНИЯ приложение спрашивает
 *    «Загрузить данные из браузера?»;
 *  - кнопка «📂 Выбрать файл» — системный выбор файла, содержимое уходит
 *    в window.KOPILKA_ANDROID_ACCEPT(base64) внутри WebView: шим
 *    распаковывает kopilka-transfer.json и записывает ВСЕ ключи в
 *    localStorage (записи, цели, события, Секретная папка и подключение
 *    к GitHub), затем перезагружает интерфейс;
 *  - «Не сейчас» — больше не спрашиваем до следующего обновления.
 *
 * НОВОЕ в v1.2 — кнопка переноса живёт ТОЛЬКО в приложении:
 *  - в браузерной версии кнопки «Перенос в приложение» больше нет;
 *  - «📲 Перенос из браузера» (в диалоге и в «Резервных копиях» через
 *    мост Android.transferPrompt()) открывает веб-версию с меткой
 *    #transfer-export — там сразу появляется экран «📥 Скачать файл
 *    переноса», т.е. весь перенос запускается из самого приложения.
 */
public class MainActivity extends Activity {

    private static final String START_URL = "file:///android_asset/index.html";
    private static final int REQ_SAVE_FILE = 8001;
    private static final int REQ_FILE_CHOOSER = 8002;
    private static final int REQ_IMPORT_FILE = 8003;

    private static final String PREFS = "kopilka_prefs";
    private static final String KEY_LAST_PROMPT = "last_prompt_version";
    private static final String WEB_URL = "https://adrinaliness.github.io/Kopilka/";

    private WebView web;
    private byte[] pendingSave;
    private String pendingSaveMime = "application/octet-stream";
    private ValueCallback<Uri[]> fileCallback;

    private String appVersion = "1.2";
    private boolean promptQueued;   // показать диалог, как только будет момент

    @SuppressLint({"SetJavaScriptEnabled"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);   /* localStorage — баланс, история, секреты */
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setTextZoom(100);

        web.addJavascriptInterface(new Bridge(), "Android");
        web.setWebViewClient(new KopilkaClient());
        web.setWebChromeClient(new KopilkaChrome());

        try {
            appVersion = getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception ignored) { }
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        String stored = prefs.getString(KEY_LAST_PROMPT, null);
        boolean firstLaunch = stored == null;
        boolean afterUpdate = stored != null && !stored.equals(appVersion);
        promptQueued = firstLaunch || afterUpdate;

        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
            queuePrompt();          /* страница уже есть — спросим чуть позже */
        } else {
            web.loadUrl(START_URL); /* спросим в onPageFinished */
        }
    }

    /* ==================== ПЕРЕНОС ДАННЫХ ИЗ БРАУЗЕРА ==================== */

    private Runnable promptRunnable = new Runnable() {
        @Override
        public void run() { maybeShowPrompt(); }
    };

    /** Запланировать показ диалога (чуть позже — чтобы активити было видно). */
    private void queuePrompt() {
        promptQueued = true;
        if (web != null) web.postDelayed(promptRunnable, 700);
    }

    private void maybeShowPrompt() {
        if (!promptQueued || isFinishing() || web == null) return;
        promptQueued = false;
        showPromptDialog();
    }

    private void showPromptDialog() { showPromptDialog(false); }

    /**
     * Диалог переноса. manual=false — автозапуск (первый запуск/обновление),
     * manual=true — вызов кнопкой «📲 Перенос из браузера» из интерфейса.
     */
    private void showPromptDialog(final boolean manual) {
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        boolean update = !manual && prefs.getString(KEY_LAST_PROMPT, null) != null;
        String title = manual
                ? "Перенос данных из браузера"
                : (update
                    ? "Копилка обновилась — загрузить данные?"
                    : "Загрузить данные из браузера?");
        String msg = (update
                ? "Версия " + appVersion + ". "
                  + "Можно подтянуть свежие данные из веб-версии.\n\n"
                : "Переедет ВСЁ из веб-версии: записи, цели, события, "
                  + "Секретная папка и подключение к GitHub.\n\n")
                + "Как перенести:\n"
                + "1. Нажми «📲 Перенос из браузера» — откроется Копилка "
                  + "в браузере\n"
                + "2. Тапни там «📥 Скачать файл переноса»\n"
                + "3. Вернись сюда → «📂 Выбрать файл» → укажи скачанный "
                  + "файл kopilka-transfer_….json";
        new AlertDialog.Builder(this)
                .setTitle(title)
                .setMessage(msg)
                .setCancelable(manual)
                .setPositiveButton("📂 Выбрать файл", new android.content.DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(android.content.DialogInterface d, int w) { openImportPicker(); }
                })
                .setNeutralButton("📲 Перенос из браузера", new android.content.DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(android.content.DialogInterface d, int w) {
                        promptQueued = true;   /* вернёмся — снова спросим */
                        try {
                            startActivity(new Intent(Intent.ACTION_VIEW,
                                    Uri.parse(WEB_URL + "#transfer-export")));
                        } catch (Exception e) {
                            toast("Браузер не найден: " + e.getMessage());
                        }
                    }
                })
                .setNegativeButton(manual ? "Закрыть" : "Не сейчас", new android.content.DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(android.content.DialogInterface d, int w) {
                        if (!manual) markPromptDone();
                    }
                })
                .show();
    }

    private void openImportPicker() {
        try {
            Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
            i.addCategory(Intent.CATEGORY_OPENABLE);
            i.setType("*/*");
            startActivityForResult(i, REQ_IMPORT_FILE);
        } catch (Exception e) {
            toast("Не смог открыть выбор файла: " + e.getMessage());
        }
    }

    /** Отдать выбранный файл в WebView — шим запишет всё в localStorage. */
    private void deliverImport(Uri uri) {
        try {
            InputStream is = getContentResolver().openInputStream(uri);
            if (is == null) throw new Exception("файл недоступен");
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int r;
            while ((r = is.read(buf)) > 0) bo.write(buf, 0, r);
            is.close();
            final String b64 = Base64.encodeToString(bo.toByteArray(), Base64.NO_WRAP);
            final String js = "(window.KOPILKA_ANDROID_ACCEPT ? KOPILKA_ANDROID_ACCEPT('"
                    + b64 + "') : 'missing')";
            web.evaluateJavascript(js, new ValueCallback<String>() {
                @Override
                public void onReceiveValue(String value) {
                    if (value != null && value.contains("ok")) {
                        markPromptDone();
                        Toast.makeText(MainActivity.this,
                                "🐷 Данные из браузера перенесены", Toast.LENGTH_LONG).show();
                    } else if (value != null && value.contains("missing")) {
                        markPromptDone();
                        Toast.makeText(MainActivity.this,
                                "Ассеты устарели — установи APK заново", Toast.LENGTH_LONG).show();
                    } else {
                        Toast.makeText(MainActivity.this,
                                "Не вышло — можно попробовать ещё раз", Toast.LENGTH_SHORT).show();
                        queuePrompt();
                    }
                }
            });
        } catch (Exception e) {
            Toast.makeText(this, "Ошибка чтения файла: " + e.getMessage(), Toast.LENGTH_SHORT).show();
            promptQueued = true;
        }
    }

    /** «Не сейчас» / успешный импорт — не спрашиваем до следующего обновления. */
    private void markPromptDone() {
        promptQueued = false;
        getSharedPreferences(PREFS, MODE_PRIVATE)
                .edit().putString(KEY_LAST_PROMPT, appVersion).apply();
    }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    /* ==================== JS-МОСТ ==================== */

    private class Bridge {
        /** Сохранение файла из JS: blob → base64 → диалог «Сохранить как». */
        @JavascriptInterface
        public void downloadFile(final String name, final String base64, final String mime) {
            try {
                pendingSave = Base64.decode(base64 == null ? "" : base64, Base64.DEFAULT);
                pendingSaveMime = (mime == null || mime.isEmpty())
                        ? "application/octet-stream" : mime;
                String safe = (name == null || name.isEmpty()) ? "kopilka_backup.json" : name;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        try {
                            Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                            i.addCategory(Intent.CATEGORY_OPENABLE);
                            i.setType(pendingSaveMime);
                            i.putExtra(Intent.EXTRA_TITLE, safe);
                            startActivityForResult(i, REQ_SAVE_FILE);
                        } catch (Exception e) {
                            toast("Не смог открыть диалог сохранения: " + e.getMessage());
                        }
                    }
                });
            } catch (Exception e) {
                toast("Ошибка файла: " + e.getMessage());
            }
        }

        @JavascriptInterface
        public void toast(final String msg) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    Toast.makeText(MainActivity.this, msg, Toast.LENGTH_SHORT).show();
                }
            });
        }

        /** Кнопка «📲 Перенос из браузера» внутри интерфейса (v1.2). */
        @JavascriptInterface
        public void transferPrompt() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() { showPromptDialog(true); }
            });
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_SAVE_FILE) {
            if (resultCode != RESULT_OK || data == null || data.getData() == null) {
                pendingSave = null;
                Toast.makeText(this, "Сохранение отменено", Toast.LENGTH_SHORT).show();
                return;
            }
            try {
                OutputStream os = getContentResolver().openOutputStream(data.getData());
                os.write(pendingSave);
                os.flush();
                os.close();
                pendingSave = null;
                Toast.makeText(this, "✅ Файл сохранён", Toast.LENGTH_SHORT).show();
            } catch (Exception e) {
                Toast.makeText(this, "Ошибка сохранения: " + e.getMessage(), Toast.LENGTH_SHORT).show();
            }
            return;
        }
        if (requestCode == REQ_IMPORT_FILE) {
            if (resultCode == RESULT_OK && data != null && data.getData() != null) {
                deliverImport(data.getData());
            } else {
                promptQueued = true;   /* отменил выбор — спросим снова в onResume */
            }
            return;
        }
        if (requestCode == REQ_FILE_CHOOSER) {
            Uri[] result = null;
            if (resultCode == RESULT_OK && data != null) {
                if (data.getClipData() != null) {
                    int n = data.getClipData().getItemCount();
                    result = new Uri[n];
                    for (int k = 0; k < n; k++) result[k] = data.getClipData().getItemAt(k).getUri();
                } else if (data.getData() != null) {
                    result = new Uri[]{data.getData()};
                }
            }
            if (fileCallback != null) {
                fileCallback.onReceiveValue(result);
                fileCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    /* ==================== WEBVIEW КЛИЕНТЫ ==================== */

    /** file:// — внутри приложения; ссылки и mailto/tel — наружу. */
    private class KopilkaClient extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri u = request.getUrl();
            String scheme = u.getScheme() == null ? "" : u.getScheme();
            if (scheme.equals("file")) return false; /* свой интерфейс */
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, u));
            } catch (Exception ignored) { }
            return true;
        }

        /** Локальные ассеты с CORS-заголовком — fetch с file://-origin не падает. */
        @Override
        public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
            Uri u = request.getUrl();
            if (u != null && "file".equals(u.getScheme())
                    && u.getPath() != null && u.getPath().startsWith("/android_asset/")) {
                try {
                    String path = u.getPath().substring("/android_asset/".length());
                    InputStream is = getAssets().open(path.isEmpty() ? "index.html" : path);
                    java.util.Map<String, String> headers = new java.util.HashMap<>();
                    headers.put("Access-Control-Allow-Origin", "*");
                    WebResourceResponse resp =
                            new WebResourceResponse(guessMime(path), "utf-8", is);
                    resp.setResponseHeaders(headers);
                    return resp;
                } catch (Exception ignored) { }
            }
            return null;
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            maybeShowPrompt();   /* страница готова — пора спрашивать */
        }
    }

    /** <input type="file"> — выбор файлов (бэкап, файлы Секретной папки). */
    private class KopilkaChrome extends WebChromeClient {
        @Override
        public boolean onShowFileChooser(WebView view,
                                         ValueCallback<Uri[]> callback,
                                         WebChromeClient.FileChooserParams params) {
            if (fileCallback != null) fileCallback.onReceiveValue(null);
            fileCallback = callback;
            try {
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");
                i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                startActivityForResult(Intent.createChooser(i, "Выберите файл"), REQ_FILE_CHOOSER);
            } catch (Exception e) {
                fileCallback = null;
                return false;
            }
            return true;
        }
    }

    private static String guessMime(String path) {
        String p = (path == null ? "" : path).toLowerCase();
        if (p.endsWith(".html") || p.endsWith(".htm")) return "text/html";
        if (p.endsWith(".js")) return "application/javascript";
        if (p.endsWith(".css")) return "text/css";
        if (p.endsWith(".json")) return "application/json";
        if (p.endsWith(".png")) return "image/png";
        if (p.endsWith(".jpg") || p.endsWith(".jpeg")) return "image/jpeg";
        if (p.endsWith(".svg")) return "image/svg+xml";
        if (p.endsWith(".webmanifest")) return "application/manifest+json";
        return "application/octet-stream";
    }

    /* ==================== ЖИЗНЕННЫЙ ЦИКЛ ==================== */

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && web != null) {
            if (web.canGoBack()) {
                web.goBack();
                return true;
            }
            moveTaskToBack(true); /* не убиваем — localStorage остаётся тёплым */
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (web != null) web.saveState(outState);
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (web != null) web.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) web.onResume();
        if (promptQueued) web.postDelayed(promptRunnable, 700);
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.removeCallbacks(promptRunnable);
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
