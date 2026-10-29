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

v1.3: + смски в фоне: карточка «💬 Смски» и шим KOPILKA_ANDROID_SMS —
журнал полученных смсок (kopilka_smslog_v1), разбор сумм из банковских
смсок и авто-добавление поступлений в доход (тумблер). SMS-приёмник —
нативный SmsReceiver (манифест), доставка — через MainActivity.
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
import glob as _glob
for _jf in sorted(_glob.glob(f"{SRC}/src/com/adrina/kopilka/*.java")):
    shutil.copy(_jf, f"{BASE}/src/com/adrina/kopilka/")
    print("  java:", os.path.basename(_jf))
shutil.copy(f"{SRC}/AndroidManifest.xml", f"{BASE}/AndroidManifest.xml")
print("AndroidManifest.xml скопирован")

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

# 2e) НОВОЕ v1.3: смски в фоне. Карточка «💬 Смски» — только в приложении
#     (в браузерной сборке её нет). Нативный SmsReceiver ловит каждую
#     новую смску даже при закрытом приложении; MainActivity отдаёт очередь
#     сюда — KOPILKA_ANDROID_SMS ведёт журнал (kopilka_smslog_v1),
#     разбирает суммы из банковских смсок и авто-добавляет поступления
#     в доход (тумблер, по умолчанию включён).
sms_card = """  <div class="card" id="smsCard">
    <h3>💬 Смски</h3>
    <div id="smsState"></div>
    <div class="row" style="margin-top:6px">
      <button class="secondary" id="smsPermBtn" onclick="try{Android.requestSmsPermission()}catch(e){showToast('Обнови приложение (APK v1.3+)')}">✅ Разрешить чтение смсок</button>
    </div>
    <label style="display:flex;align-items:center;gap:8px;margin-top:8px;cursor:pointer">
      <input type="checkbox" id="smsAutoAdd" onchange="smsAutoToggle(this.checked)">
      <span>Авто-добавлять поступления из смсок в доход</span>
    </label>
    <div id="smsList" style="margin-top:8px"></div>
  </div>

"""
marker_sms = '</div><!-- /page-income -->'
assert marker_sms in html, "маркер /page-income не найден"
html = html.replace(marker_sms, sms_card + marker_sms, 1)

sms_shim = """<script>
/* [KOPILKA ANDROID v1.3] смски в фоне: журнал + разбор сумм + авто-доход */
(function(){
'use strict';
var K = { log: 'kopilka_smslog_v1', auto: 'kopilka_sms_auto_v1' };
window.smsEsc = function (s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
};
window.smsParseSms = function (body) {
  var t = String(body || '').toLowerCase().replace(/\\u00a0/g, ' ');
  var isIn = /(поступ|зачисл|перевод|пополнен|внесен|приход|начислен)/.test(t);
  var isOut = /(списан|списание|оплат|покупк|платеж|платёж|снятие|потрат)/.test(t);
  var m = t.match(/(\\d[\\d\\s.,]{0,14})\\s*(?:руб|rub|₽|р(?![а-яa-z]))/);
  var amount = 0;
  if (m) amount = parseFloat(m[1].replace(/[^\\d.,]/g, '').replace(',', '.')) || 0;
  return { amount: amount, dir: isIn ? 'in' : (isOut ? 'out' : '') };
};
window.smsAddIncome = function (amount) {
  try {
    entries.push({ id: Date.now(), date: todayStr(), hours: 0, earned: amount,
                   category: 'Смска', gift: false, createdAt: Date.now(), sms: true });
    saveIncome(); renderIncome(); updateEvents(); playCoin();
    return true;
  } catch (e) { return false; }
};
window.smsAutoToggle = function (on) {
  try { localStorage.setItem(K.auto, on ? '1' : '0'); } catch (e) {}
  try { showToast(on ? '✅ Поступления из смсок — сразу в доход' : '🙈 Авто-добавление выключено — добавляй вручную «➕ в доход»'); } catch (e) {}
};
window.smsActionByKey = function (enc, act) {
  try {
    var key = JSON.parse(decodeURIComponent(enc));
    var list = JSON.parse(localStorage.getItem(K.log) || '[]');
    for (var i = 0; i < list.length; i++) {
      if (list[i].key !== key) continue;
      if (act === 'add') {
        if (!list[i].added && list[i].amount > 0 && smsAddIncome(list[i].amount)) {
          list[i].added = true;
          showToast('🐷 +' + fmt(list[i].amount) + ' ₽ записано в доход');
        }
      } else if (act === 'del') {
        list.splice(i, 1);
        showToast('🗑 Удалено из журнала');
      }
      break;
    }
    localStorage.setItem(K.log, JSON.stringify(list));
    smsRenderCard();
  } catch (e) { try { showToast('Не получилось: ' + e); } catch (e2) {} }
};
window.smsRenderCard = function () {
  var card = document.getElementById('smsCard'); if (!card) return;
  var granted = false;
  try { granted = (window.Android && Android.smsPermissionState) ? Android.smsPermissionState() === 'granted' : false; } catch (e) {}
  var st = document.getElementById('smsState');
  if (st) st.innerHTML = granted
    ? '<div class="muted" style="margin-bottom:6px">✅ Смски читаются в фоне: каждая новая появится в журнале, а поступления — сразу в доходе (даже если приложение закрыто).</div>'
    : '<div class="muted" style="margin-bottom:6px">🔕 Чтение выключено (нужно разрешение). Включи — и поступления из банковских смсок будут попадать в Копилку сами.</div>';
  var btn = document.getElementById('smsPermBtn');
  if (btn) btn.style.display = granted ? 'none' : '';
  var box = document.getElementById('smsList'); if (!box) return;
  var list = [];
  try { list = JSON.parse(localStorage.getItem(K.log) || '[]'); } catch (e) {}
  if (!list.length) { box.innerHTML = '<div class="muted">Пока пусто — как только придёт смска, она появится здесь.</div>'; return; }
  var rows = list.slice(0, 20).map(function (e) {
    var d = new Date(e.ts || Date.now());
    var dd = String(d.getDate()).padStart(2, '0') + '.' + String(d.getMonth() + 1).padStart(2, '0')
           + ' ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
    var sum = e.amount ? ' — <b>' + fmt(e.amount) + ' ₽' + (e.added ? ' ✅ в доход' : '') + '</b>' : '';
    var enc = encodeURIComponent(JSON.stringify(e.key));
    var acts = '';
    if (e.amount && !e.added) acts += ' <button class="ghost mini-btn" onclick="smsActionByKey(\\'' + enc + '\\',\\'add\\')">➕ в доход</button>';
    acts += ' <button class="ghost mini-btn" onclick="smsActionByKey(\\'' + enc + '\\',\\'del\\')">🗑</button>';
    return '<div style="margin:4px 0;padding:6px 8px;border:1px solid var(--input-border);border-radius:10px"><b>' + smsEsc(e.from) + '</b> <span class="muted">' + dd + '</span>' + sum
         + '<div style="margin-top:2px;word-break:break-word">' + smsEsc(e.body) + '</div>'
         + '<div style="margin-top:4px">' + acts + '</div></div>';
  }).join('');
  box.innerHTML = rows;
};
window.KOPILKA_ANDROID_SMS = function (b64) {
  try {
    var bin = atob(String(b64 || ''));
    var u8 = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    var items = JSON.parse(new TextDecoder('utf-8').decode(u8));
    if (!items || !items.length) return 'ok';
    var list = [];
    try { list = JSON.parse(localStorage.getItem(K.log) || '[]'); } catch (e) {}
    var auto = null; try { auto = localStorage.getItem(K.auto); } catch (e) {}
    var autoOn = (auto === null) ? true : auto === '1';
    var addedSum = 0, addedN = 0, fresh = 0;
    for (var k = 0; k < items.length; k++) {
      var it = items[k] || {}; if (!it.body) continue;
      var key = String(it.ts || 0) + '|' + String(it.from || '') + '|' + String(it.body || '');
      var dup = false;
      for (var j = 0; j < list.length; j++) if (list[j].key === key) { dup = true; break; }
      if (dup) continue;
      var p = smsParseSms(it.body);
      list.unshift({ key: key, ts: it.ts || Date.now(), from: it.from || '', body: it.body, amount: p.amount, dir: p.dir, added: false });
      fresh++;
      if (autoOn && p.amount > 0 && p.dir === 'in' && smsAddIncome(p.amount)) {
        list[0].added = true; addedSum += p.amount; addedN++;
      }
    }
    if (list.length > 100) list.length = 100;
    localStorage.setItem(K.log, JSON.stringify(list));
    try { smsRenderCard(); } catch (e) {}
    if (addedN > 0) { try { showToast('🐷 Из смсок в доход: +' + fmt(addedSum) + ' ₽'); } catch (e) {} }
    else if (fresh > 0) { try { showToast('💬 Новых смсок: ' + fresh); } catch (e) {} }
    return 'ok';
  } catch (e) { return 'error'; }
};
window.KOPILKA_SMS_REFRESH = function () { try { smsRenderCard(); } catch (e) {} return 'ok'; };
var cb = document.getElementById('smsAutoAdd');
if (cb) { var v = null; try { v = localStorage.getItem(K.auto); } catch (e) {} cb.checked = (v === null) ? true : v === '1'; }
try { smsRenderCard(); } catch (e) {}
console.log('%c[KOPILKA ANDROID] sms-ready','color:#2ecc71;font-weight:bold');
})();
</script>"""
close_body = html.rindex("</body>")
html = html[:close_body] + sms_shim + "\n" + html[close_body:]
io.open(f"{BASE}/assets/index.html", "w", encoding="utf-8").write(html)
print("index.html:", len(html), "bytes (+ download-shim + перенос v1.2 + смски v1.3)")

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
