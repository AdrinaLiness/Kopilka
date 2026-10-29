#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Подготовка проекта kopilka_android: ассеты (локальный Chart.js), иконка.

v1.1: + шим KOPILKA_ANDROID_ACCEPT — приём файла переноса
(kopilka-transfer.json) из нативного диалога: все ключи localStorage
восстанавливаются целиком, включая подключение к GitHub и Секретную папку.

v1.2: + кнопка «📲 Перенос из браузера» ТОЛЬКО в приложении (в блоке
«Резервные копии»): через мост Android.transferPrompt() открывает нативный
диалог переноса; в браузерной версии такой кнопки больше нет — она там
не нужна (перенос запускается из самого приложения).
"""
import io
import json
import os
import shutil

BASE = "/home/z/my-project/kopilka_android"
SITE = "/home/z/my-project/kopilka_repo"          # свежие файлы из репо (с правками v1.1)
CHART_LOCAL = "/home/z/my-project/android-sdk/dl/chart.umd.min.js"
CHART_URL = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"

os.makedirs(f"{BASE}/assets", exist_ok=True)
os.makedirs(f"{BASE}/res/drawable", exist_ok=True)
os.makedirs(f"{BASE}/src/com/adrina/kopilka", exist_ok=True)

# 0) Java-исходники и манифест из репо → рабочий проект
SRC = "/home/z/my-project/kopilka_repo/ANDROID/source"
shutil.copy(f"{SRC}/src/com/adrina/kopilka/MainActivity.java",
            f"{BASE}/src/com/adrina/kopilka/MainActivity.java")
shutil.copy(f"{SRC}/AndroidManifest.xml", f"{BASE}/AndroidManifest.xml")
print("MainActivity.java + AndroidManifest.xml скопированы")

# 1) Chart.js локально
if os.path.exists(CHART_LOCAL):
    chart = io.open(CHART_LOCAL, "rb").read()
else:
    import urllib.request
    chart = urllib.request.urlopen(CHART_URL, timeout=60).read()
io.open(f"{BASE}/assets/chart.umd.min.js", "wb").write(chart)
print("chart.umd.min.js:", len(chart), "bytes")

# 2) index.html: CDN → локальный файл
html = io.open(f"{SITE}/index.html", encoding="utf-8").read()
old = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js">'
assert old in html, "тег Chart.js не найден"
html = html.replace(old, '<script src="chart.umd.min.js"></script>')
# страховка: если Chart не загрузился — графики не роняют приложение
guard = """<script>
/* [KOPILKA ANDROID] страховка: если Chart недоступен — стаб-заглушка */
window.addEventListener('error', function(e){
  if (e && e.message && /Chart is not defined/i.test(e.message)) {
    console.warn('[KOPILKA ANDROID] Chart.js недоступен — графики отключены');
  }
}, true);
</script>"""
html = html.replace("</head>", guard + "\n</head>", 1)

# 2b) Шим скачивания: blob + a[download] → нативный мост Android.downloadFile
#     (в Android WebView a.click() с blob: не сохраняет файл сам по себе)
shim = """<script>
/* [KOPILKA ANDROID] blob-скачивания → нативный диалог «Сохранить как» */
(function(){
'use strict';
if(!window.Android || !Android.downloadFile) return;
var origClick = HTMLAnchorElement.prototype.click;
HTMLAnchorElement.prototype.click = function(){
  try{
    var dl = this.getAttribute && this.getAttribute('download');
    if (dl && typeof this.href === 'string' && this.href.indexOf('blob:') === 0){
      var self = this;
      fetch(this.href).then(function(r){ return r.blob(); }).then(function(b){
        var fr = new FileReader();
        fr.onload = function(){
          try{
            var b64 = String(fr.result).split(',')[1] || '';
            Android.downloadFile(String(dl), b64, b.type || 'application/octet-stream');
          }catch(e){
            try{ showToast('❌ Не удалось сохранить файл: ' + e); }catch(e2){}
          }
        };
        fr.readAsDataURL(b);
      }).catch(function(){ origClick.call(self); });
      return;
    }
  }catch(e){}
  origClick.call(this);
};
console.log('%c[KOPILKA ANDROID] download-shim установлен','color:#2ecc71;font-weight:bold');
})();
</script>"""
close_body = html.rindex("</body>")
html = html[:close_body] + shim + "\n" + html[close_body:]

# 2c) НОВОЕ v1.1: приём файла переноса из нативного диалога (MainActivity
#     вызывает KOPILKA_ANDROID_ACCEPT(base64) — шим пишет все ключи в
#     localStorage и перезагружает интерфейс). Зашифрованные копии
#     (kopilka-secret) импортируются штатно через «Резервные копии».
accept_shim = """<script>
/* [KOPILKA ANDROID v1.1] приём файла переноса (kopilka-transfer.json) */
window.KOPILKA_ANDROID_ACCEPT = function(b64){
  try{
    var bin = atob(String(b64 || ''));
    var u8 = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    var parsed = JSON.parse(new TextDecoder('utf-8').decode(u8));
    if (parsed && parsed.app === 'kopilka-transfer' && parsed.keys) {
      var n = 0;
      for (var k in parsed.keys) {
        if (Object.prototype.hasOwnProperty.call(parsed.keys, k)) {
          try { localStorage.setItem(k, String(parsed.keys[k])); n++; } catch(e){}
        }
      }
      var ghOk = !!parsed.keys['income_tracker_gh_v1'];
      try { showToast('✅ Перенесено блоков: ' + n + (ghOk ? ' · GitHub подключён' : '')); } catch(e){}
      setTimeout(function(){ location.reload(); }, 700);
      return 'ok';
    }
    if (parsed && parsed.app === 'kopilka-secret') {
      try { showToast('🔐 Файл зашифрован — импортируй через «Резервные копии» в приложении'); } catch(e){}
      return 'encrypted';
    }
    if (parsed && parsed.entries) {
      /* обычный незашифрованный JSON-бэкап — восстановим то, что в нём есть */
      var map = { entries:'income_tracker_v2', settings:'income_tracker_settings_v2',
                  feeds:'income_tracker_feed_v1', drops:'income_tracker_drops_v1',
                  games:'income_tracker_games_v1', wishes:'income_tracker_wishes_v1',
                  events:'income_tracker_events_v1' };
      var n2 = 0;
      for (var f in map) {
        if (Object.prototype.hasOwnProperty.call(map, f) && parsed[f] !== undefined) {
          localStorage.setItem(map[f], JSON.stringify(parsed[f])); n2++;
        }
      }
      try { showToast('✅ Восстановлено блоков: ' + n2); } catch(e){}
      setTimeout(function(){ location.reload(); }, 700);
      return 'ok';
    }
    try { showToast('❌ Это не файл переноса Копилки'); } catch(e){}
    return 'unknown';
  }catch(e){
    try { showToast('❌ Не удалось прочитать файл: ' + e); } catch(e2){}
    return 'error';
  }
};
console.log('%c[KOPILKA ANDROID] transfer-import готов','color:#2ecc71;font-weight:bold');
</script>"""
close_body = html.rindex("</body>")
html = html[:close_body] + accept_shim + "\n" + html[close_body:]

# 2d) НОВОЕ v1.2: кнопка «📲 Перенос из браузера» — ТОЛЬКО внутри
#     приложения (в браузерной сборке её нет). Открывает нативный диалог
#     переноса: он сам откроет веб-версию с #transfer-export (экран
#     «📥 Скачать файл переноса»), а дальше — «📂 Выбрать файл».
transfer_btn = ('<button class="secondary" '
                'onclick="try{Android.transferPrompt()}catch(e){showToast(\'Обнови приложение (APK v1.2+)\')}">'
                '📲 Перенос из браузера</button>\n    ')
marker_btn = '<button class="danger" onclick="resetAll()">Удалить все данные</button>'
assert marker_btn in html, "маркер кнопки «Удалить все данные» не найден"
html = html.replace(marker_btn, transfer_btn + marker_btn, 1)
io.open(f"{BASE}/assets/index.html", "w", encoding="utf-8").write(html)
print("index.html:", len(html), "bytes (Chart.js локализован + download-shim + transfer-import + кнопка переноса)")

# 3) sw.js — кладём для полноты (на file:// регистрация безопасно пропускается)
shutil.copy(f"{SITE}/sw.js", f"{BASE}/assets/sw.js")

# 4) Иконка: свинка из pig.png → квадрат 192
from PIL import Image, ImageDraw
pig = Image.open("/home/z/my-project/scripts/pig.png").convert("RGBA")
crop = pig.crop((40, 0, 160, 120)).resize((200, 200), Image.LANCZOS)
canvas = Image.new("RGBA", (192, 192), (0, 0, 0, 0))
d = ImageDraw.Draw(canvas)
d.rounded_rectangle([2, 2, 190, 190], radius=42, fill=(253, 231, 239, 255),
                    outline=(244, 194, 213, 255), width=3)
inner = crop.resize((168, 168), Image.LANCZOS)
mask = Image.new("L", (168, 168), 0)
ImageDraw.Draw(mask).ellipse([0, 0, 168, 168], fill=255)
canvas.paste(inner, (12, 12), mask)
canvas.save(f"{BASE}/res/drawable/ic_launcher.png")
print("ic_launcher.png: 192x192 OK")

# 5) проверка ассетов
for f in sorted(os.listdir(f"{BASE}/assets")):
    print("  asset:", f, os.path.getsize(f"{BASE}/assets/" + f))

# 6) синтакс-проверка JS из собранного index.html (все <script> без src)
import re
blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
bad = 0
for i, b in enumerate(blocks):
    if not b.strip():
        continue
    io.open(f"{BASE}/out_check_{i}.js", "w", encoding="utf-8").write(b)
    rc = os.system(f"node --check {BASE}/out_check_{i}.js >/dev/null 2>&1")
    if rc != 0:
        bad += 1
        print(f"  ⚠️ JS-блок #{i} не прошёл node --check")
    os.remove(f"{BASE}/out_check_{i}.js")
print("JS-блоков проверено:", len(blocks), "ошибок:", bad)
assert bad == 0, "есть ошибки синтаксиса JS"
print("OK: проект подготовлен")
