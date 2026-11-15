"""
Aile Konum - Sunucu (yönetim paneli + Google Haritalar bağlantısı)
Kurulum : pip install flask gunicorn
Çalıştır: AILE_KODU=sifren ADMIN_KODU=yonetici-sifren gunicorn -w 1 -b 0.0.0.0:5000 server:app
Aile haritası : /        (AILE_KODU ile)
Yönetim paneli: /admin   (ADMIN_KODU ile; ADMIN_KODU tanımlı değilse panel kapalıdır)
"""
import hmac
import json
import os
import threading
import time

from flask import Flask, Response, jsonify, request

AILE_KODU = os.environ.get("AILE_KODU", "degistir-beni")
ADMIN_KODU = os.environ.get("ADMIN_KODU", "")
DOSYA = os.environ.get("DATA_FILE", "konumlar.json")
BAGLI_SANIYE = 300  # son 5 dk içinde konum geldiyse "bağlı"

app = Flask(__name__)
kilit = threading.Lock()
kisiler = {}      # isim -> {lat, lon, zaman(sn)}
engelli = set()   # engellenen isimler
basarisiz = {}    # ip -> başarısız yönetici girişi zamanları

try:
    with open(DOSYA, encoding="utf-8") as f:
        _veri = json.load(f)
    if "kisiler" in _veri and "engelli" in _veri:
        kisiler = _veri["kisiler"]
        engelli = set(_veri["engelli"])
    else:
        kisiler = _veri
except (OSError, ValueError, TypeError):
    pass


def kaydet():
    try:
        with open(DOSYA, "w", encoding="utf-8") as f:
            json.dump({"kisiler": kisiler, "engelli": sorted(engelli)}, f)
    except OSError:
        pass


def kod_ok(kod, beklenen=AILE_KODU):
    return isinstance(kod, str) and hmac.compare_digest(kod.encode(), beklenen.encode())


def admin_ok(d):
    if not ADMIN_KODU:
        return False
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    simdi = time.time()
    kayit = [t for t in basarisiz.get(ip, []) if simdi - t < 600]
    basarisiz[ip] = kayit
    if len(kayit) >= 10:  # 10 dk içinde 10 yanlış deneme: geçici kilit
        return False
    if kod_ok(d.get("admin"), ADMIN_KODU):
        return True
    kayit.append(simdi)
    return False


HTML = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aile Konumu</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body{margin:0;font-family:sans-serif;display:flex;flex-direction:column;height:100vh}
#bar{padding:8px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
#map{flex:1;min-height:200px}
#list{max-height:35vh;overflow:auto;border-top:1px solid #ccc}
.kisi{display:flex;align-items:center;gap:8px;padding:8px;border-bottom:1px solid #eee;flex-wrap:wrap}
.kisi b{flex:1;min-width:90px}
.kisi a,.kisi button{font-size:14px;padding:6px 10px;border:1px solid #888;border-radius:4px;background:#f4f4f4;color:#000;text-decoration:none;cursor:pointer}
input,button{padding:8px;font-size:15px}
</style></head><body>
<div id="bar">
  <input id="code" type="password" placeholder="Aile kodu">
  <button onclick="yenile()">Göster</button>
  <span id="st"></span>
</div>
<div id="map"></div>
<div id="list"></div>
<script>
const map = L.map('map').setView([39, 35], 6);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {attribution: '&copy; OpenStreetMap'}).addTo(map);
const $ = id => document.getElementById(id);
let markers = {}, ilk = true;
$('code').value = localStorage.getItem('kod') || '';

const esc = s => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function ne(s) {
  if (s < 90) return s + ' sn önce';
  if (s < 5400) return Math.round(s / 60) + ' dk önce';
  if (s < 172800) return Math.round(s / 3600) + ' sa önce';
  return Math.round(s / 86400) + ' gün önce';
}
function gmaps(lat, lon) {
  return 'https://www.google.com/maps/search/?api=1&query=' + lat + ',' + lon;
}

function listeyiYaz(veri) {
  const l = $('list');
  l.textContent = '';
  Object.keys(veri).sort().forEach(ad => {
    const k = veri[ad];
    const d = document.createElement('div'); d.className = 'kisi';
    const b = document.createElement('b'); b.textContent = ad;
    const t = document.createElement('span'); t.textContent = ne(k.saniye);
    const a = document.createElement('a');
    a.textContent = 'Google Haritalar'; a.target = '_blank'; a.rel = 'noopener';
    a.href = gmaps(k.lat, k.lon);
    const g = document.createElement('button'); g.textContent = 'Haritada göster';
    g.onclick = () => { map.setView([k.lat, k.lon], 16); if (markers[ad]) markers[ad].openPopup(); };
    d.append(b, t, a, g);
    l.append(d);
  });
}

async function yenile() {
  const kod = $('code').value;
  if (!kod) return;
  const r = await fetch('/api/locations?code=' + encodeURIComponent(kod));
  if (!r.ok) { $('st').textContent = 'Kod yanlış'; return; }
  localStorage.setItem('kod', kod);
  $('st').textContent = '';
  const veri = await r.json();
  for (const ad in markers) if (!(ad in veri)) { map.removeLayer(markers[ad]); delete markers[ad]; }
  for (const ad in veri) {
    const {lat, lon, saniye} = veri[ad];
    const metin = esc(ad) + ' (' + ne(saniye) + ')';
    const popup = '<b>' + esc(ad) + '</b><br>' + ne(saniye) +
      '<br><a target="_blank" rel="noopener" href="' + gmaps(lat, lon) + '">Google Haritalar ile aç</a>';
    if (markers[ad]) {
      markers[ad].setLatLng([lat, lon]).setTooltipContent(metin).setPopupContent(popup);
    } else {
      markers[ad] = L.marker([lat, lon]).addTo(map)
        .bindTooltip(metin, {permanent: true, direction: 'top'}).bindPopup(popup);
    }
  }
  listeyiYaz(veri);
  const m = Object.values(markers);
  if (ilk && m.length) { map.fitBounds(m.map(x => x.getLatLng()), {padding: [50, 50], maxZoom: 15}); ilk = false; }
}
setInterval(yenile, 10000);
yenile();
</script></body></html>"""


ADMIN_HTML = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aile Konum - Yönetim</title>
<style>
body{font-family:sans-serif;margin:16px}
table{border-collapse:collapse;width:100%;margin-top:12px}
td,th{border-bottom:1px solid #ddd;padding:8px;text-align:left}
.on{color:#0a7a0a;font-weight:bold}.off{color:#888}.blk{color:#c00;font-weight:bold}
button,input{padding:7px 10px;font-size:14px;margin-right:4px}
</style></head><body>
<h2>Aile Konum - Yönetim</h2>
<input id="kod" type="password" placeholder="Yönetici kodu">
<button onclick="yenile()">Giriş / Yenile</button>
<span id="st"></span>
<p id="ozet"></p>
<table>
<thead><tr><th>Ad</th><th>Durum</th><th>Son konum</th><th>Harita</th><th>İşlem</th></tr></thead>
<tbody id="tb"></tbody>
</table>
<script>
const $ = id => document.getElementById(id);
function ne(s) {
  if (s === null) return '-';
  if (s < 90) return s + ' sn önce';
  if (s < 5400) return Math.round(s / 60) + ' dk önce';
  if (s < 172800) return Math.round(s / 3600) + ' sa önce';
  return Math.round(s / 86400) + ' gün önce';
}
function api(yol, veri) {
  return fetch(yol, {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(Object.assign({admin: $('kod').value}, veri || {}))});
}
async function islem(yol, ad) { await api(yol, {ad: ad}); yenile(); }
function hucre(tr, metin) {
  const td = document.createElement('td'); td.textContent = metin; tr.append(td); return td;
}
async function yenile() {
  if (!$('kod').value) return;
  const r = await api('/api/admin/list');
  if (!r.ok) { $('st').textContent = 'Kod yanlış, yönetim kapalı ya da çok fazla deneme'; return; }
  $('st').textContent = '';
  const v = await r.json();
  const tb = $('tb'); tb.textContent = '';
  let bagli = 0;
  v.forEach(k => {
    const tr = document.createElement('tr');
    let durum = 'Çevrimdışı', sinif = 'off';
    if (k.engelli) { durum = 'Engelli'; sinif = 'blk'; }
    else if (k.saniye !== null && k.saniye < __BAGLI__) { durum = 'Bağlı'; sinif = 'on'; bagli++; }
    hucre(tr, k.ad).style.fontWeight = 'bold';
    hucre(tr, durum).className = sinif;
    hucre(tr, ne(k.saniye));
    const kt = document.createElement('td');
    if (k.lat !== null) {
      const a = document.createElement('a');
      a.textContent = 'Google Haritalar'; a.target = '_blank'; a.rel = 'noopener';
      a.href = 'https://www.google.com/maps/search/?api=1&query=' + k.lat + ',' + k.lon;
      kt.append(a);
    } else kt.textContent = '-';
    tr.append(kt);
    const it = document.createElement('td');
    const b1 = document.createElement('button');
    b1.textContent = k.engelli ? 'Engeli kaldır' : 'Engelle';
    b1.onclick = () => islem(k.engelli ? '/api/admin/unblock' : '/api/admin/block', k.ad);
    const b2 = document.createElement('button');
    b2.textContent = 'Sil';
    b2.onclick = () => { if (confirm(k.ad + ' kaydı silinsin mi?')) islem('/api/admin/delete', k.ad); };
    it.append(b1, b2);
    tr.append(it);
    tb.append(tr);
  });
  $('ozet').textContent = 'Toplam ' + v.length + ' kişi, şu an bağlı: ' + bagli +
    ' (son 5 dk içinde konum gelenler)';
}
setInterval(yenile, 15000);
</script></body></html>""".replace("__BAGLI__", str(BAGLI_SANIYE))


@app.route("/")
def ana():
    return Response(HTML, mimetype="text/html")


@app.route("/admin")
def admin_sayfa():
    return Response(ADMIN_HTML, mimetype="text/html")


@app.route("/api/update", methods=["POST"])
def guncelle():
    d = request.get_json(silent=True) or {}
    if not kod_ok(d.get("code")):
        return jsonify(hata="kod"), 403
    try:
        ad = str(d["name"]).strip()[:30]
        lat, lon = float(d["lat"]), float(d["lon"])
        zaman = min(float(d.get("time", time.time() * 1000)) / 1000, time.time())
    except (KeyError, ValueError, TypeError):
        return jsonify(hata="veri"), 400
    if not ad or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify(hata="veri"), 400
    with kilit:
        if ad in engelli:
            return jsonify(hata="engelli"), 403
        eski = kisiler.get(ad)
        if not eski or zaman >= eski["zaman"]:
            kisiler[ad] = {"lat": lat, "lon": lon, "zaman": zaman}
            kaydet()
    return jsonify(ok=True)


@app.route("/api/locations")
def konumlar():
    if not kod_ok(request.args.get("code")):
        return jsonify(hata="kod"), 403
    simdi = time.time()
    with kilit:
        return jsonify({
            ad: {"lat": k["lat"], "lon": k["lon"], "saniye": int(simdi - k["zaman"])}
            for ad, k in kisiler.items() if ad not in engelli})


# ---------------- Yönetim ----------------
@app.route("/api/admin/list", methods=["POST"])
def admin_liste():
    d = request.get_json(silent=True) or {}
    if not admin_ok(d):
        return jsonify(hata="kod"), 403
    simdi = time.time()
    cikti = []
    with kilit:
        for ad in sorted(set(kisiler) | engelli):
            k = kisiler.get(ad)
            cikti.append({
                "ad": ad,
                "engelli": ad in engelli,
                "lat": k["lat"] if k else None,
                "lon": k["lon"] if k else None,
                "saniye": int(simdi - k["zaman"]) if k else None})
    return jsonify(cikti)


def _admin_islem(islem):
    d = request.get_json(silent=True) or {}
    if not admin_ok(d):
        return jsonify(hata="kod"), 403
    ad = str(d.get("ad", "")).strip()[:30]
    if not ad:
        return jsonify(hata="veri"), 400
    with kilit:
        islem(ad)
        kaydet()
    return jsonify(ok=True)


@app.route("/api/admin/block", methods=["POST"])
def admin_engelle():
    return _admin_islem(lambda ad: engelli.add(ad))


@app.route("/api/admin/unblock", methods=["POST"])
def admin_engel_kaldir():
    return _admin_islem(lambda ad: engelli.discard(ad))


@app.route("/api/admin/delete", methods=["POST"])
def admin_sil():
    def sil(ad):
        kisiler.pop(ad, None)
        engelli.discard(ad)
    return _admin_islem(sil)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
