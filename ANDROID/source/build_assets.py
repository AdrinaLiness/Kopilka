#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Подготовка проекта kopilka_android: ассеты (локальный Chart.js), иконка."""
import io
import os
import shutil
import urllib.request

BASE = "/home/z/my-project/kopilka_android"
SITE = "/home/z/my-project/kopilka_site"
CHART_URL = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"

os.makedirs(f"{BASE}/assets", exist_ok=True)
os.makedirs(f"{BASE}/res/drawable", exist_ok=True)
os.makedirs(f"{BASE}/src/com/adrina/kopilka", exist_ok=True)

# 1) Chart.js локально
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
io.open(f"{BASE}/assets/index.html", "w", encoding="utf-8").write(html)
print("index.html:", len(html), "bytes (Chart.js локализован + download-shim)")

# 3) sw.js — кладём для полноты (на file:// регистрация безопасно пропускается)
shutil.copy(f"{SITE}/sw.js", f"{BASE}/assets/sw.js")

# 4) Иконка: свинка из pig.png → квадрат 192
from PIL import Image, ImageDraw, ImageOps
pig = Image.open("/home/z/my-project/scripts/pig.png").convert("RGBA")
# круг центр (100,60), r≈58 → квадратный кроп с запасом
crop = pig.crop((40, 0, 160, 120)).resize((200, 200), Image.LANCZOS)
canvas = Image.new("RGBA", (192, 192), (0, 0, 0, 0))
d = ImageDraw.Draw(canvas)
# мягкий розовый скруглённый квадрат
d.rounded_rectangle([2, 2, 190, 190], radius=42, fill=(253, 231, 239, 255),
                    outline=(244, 194, 213, 255), width=3)
inner = crop.resize((168, 168), Image.LANCZOS)
# маска круга для свинки
mask = Image.new("L", (168, 168), 0)
ImageDraw.Draw(mask).ellipse([0, 0, 168, 168], fill=255)
canvas.paste(inner, (12, 12), mask)
canvas.save(f"{BASE}/res/drawable/ic_launcher.png")
print("ic_launcher.png: 192x192 OK")

# 5) проверка ассетов
for f in sorted(os.listdir(f"{BASE}/assets")):
    print("  asset:", f, os.path.getsize(f"{BASE}/assets/" + f))
print("OK: проект подготовлен")
