import os, io, requests
from collections import Counter
from PIL import Image

key = os.environ["AEMET_API_KEY"]
r = requests.get(
    "https://opendata.aemet.es/opendata/api/red/radar/regional/pm",
    headers={"api_key": key, "accept": "application/json"},
    timeout=30,
)
print("AEMET:", r.status_code, r.text[:80].replace(key, "***"))
r.raise_for_status()
j = r.json()
g = requests.get(j["datos"], timeout=60)
print("Descarga:", g.status_code, len(g.content), "bytes")
g.raise_for_status()
os.makedirs("radar", exist_ok=True)
with open("radar/raw.gif", "wb") as f:
    f.write(g.content)
im = Image.open(io.BytesIO(g.content)).convert("RGB")
print("Tamaño:", im.size)
for color, n in Counter(im.getdata()).most_common(30):
    print(color, n)
