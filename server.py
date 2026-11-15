"""
Aile Konum - Sunucu
Kurulum : pip install flask gunicorn
Çalıştır: AILE_KODU=sifren gunicorn -w 1 -b 0.0.0.0:5000 server:app
(Windows'ta test için: set AILE_KODU=sifren  ve  python server.py)
Telefonlar konumu /api/update adresine gönderir, harita sayfası / adresindedir.
"""
import hmac
import json
import os
import threading
import time

from flask import Flask, Response, jsonify, request

AILE_KODU = os.environ.get("AILE_KODU", "degistir-beni")
DOSYA = os.environ.get("DATA_FILE", "konumlar.json")

app = Flask(__name__)
kilit = threading.Lock()
kisiler = {}  # isim -> {lat, lon, zaman(sn)}

try:
    with open(DOSYA, encoding="utf-8") as f:
        kisiler = json.load(f)
except (OSError, ValueError):
    pass


def kaydet():
    try:
        with open(DOSYA, "w", encoding="utf-8") as f:
            json.dump(kisiler, f)
    except OSError:
        pass


def kod_ok(kod):
    return isinstance(kod, str) and hmac.compare_digest(kod.encode(), AILE_KODU.encode())


HTML = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aile Konumu</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body{margin:0;font-family:sans-serif}
#bar{padding:8px;display:flex;gap:6px;align-items:center}
#map{height:calc(100vh - 56px)}
input,button{padding:8px;font-size:15px}
</style></head><body>
<div id="bar">
  <input id="code" type="password" placeholder="Aile kodu">
  <button onclick="yenile()">Göster</button>
  <span id="st"></span>
</div>
<div id="map"></div>
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
    if (markers[ad]) markers[ad].setLatLng([lat, lon]).setTooltipContent(metin);
    else markers[ad] = L.marker([lat, lon]).addTo(map)
      .bindTooltip(metin, {permanent: true, direction: 'top'});
  }
  const m = Object.values(markers);
  if (ilk && m.length) { map.fitBounds(m.map(x => x.getLatLng()), {padding: [50, 50], maxZoom: 15}); ilk = false; }
}
setInterval(yenile, 10000);
yenile();
</script></body></html>"""


@app.route("/")
def ana():
    return Response(HTML, mimetype="text/html")


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
            for ad, k in kisiler.items()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
