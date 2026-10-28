package com.adrina.kopilka;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.util.Base64;
import android.view.KeyEvent;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.ByteArrayInputStream;
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
 */
public class MainActivity extends Activity {

    private static final String START_URL = "file:///android_asset/index.html";
    private static final int REQ_SAVE_FILE = 8001;
    private static final int REQ_FILE_CHOOSER = 8002;

    private WebView web;
    private byte[] pendingSave;
    private String pendingSaveMime = "application/octet-stream";
    private android.webkit.ValueCallback<Uri[]> fileCallback;

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

        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
        } else {
            web.loadUrl(START_URL);
        }
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
    }

    /** <input type="file"> — выбор файлов (бэкап, файлы Секретной папки). */
    private class KopilkaChrome extends WebChromeClient {
        @Override
        public boolean onShowFileChooser(WebView view,
                                         android.webkit.ValueCallback<Uri[]> callback,
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
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
