import io, json, os, time, datetime, email.utils
from collections import Counter
import requests
from PIL import Image

RADAR = "pm"  # Illes Balears
URL = "https://opendata.aemet.es/opendata/api/red/radar/regional/" + RADAR
MAPA = 480    # el mapa ocupa las 480 primeras filas; debajo va la leyenda

# Colores de la escala de AEMET -> nivel
# 0 debil (12-30 dBZ), 1 moderada (30-42), 2 fuerte (42-54), 3 severa (54 o mas)
PALETA = {
    (0, 0, 252): 0, (0, 148, 252): 0, (0, 252, 252): 0,
    (67, 131, 35): 1, (0, 192, 0): 1,
    (0, 255, 0): 2, (255, 255, 0): 2,
    (255, 187, 0): 3, (255, 127, 0): 3, (255, 0, 0): 3, (200, 0, 90): 3,
}
# Tus colores (R, G, B, transparencia)
COLORES = {
    0: (0, 200, 0, 200),      # verde
    1: (255, 230, 0, 220),    # amarillo
    2: (255, 0, 0, 230),      # rojo
    3: (150, 0, 220, 240),    # morado
}
COSTA = "radar/costa.png"


def descargar():
    key = os.environ["AEMET_API_KEY"]
    cab = {"api_key": key, "accept": "application/json"}
    for intento in range(3):
        try:
            r = requests.get(URL, headers=cab, timeout=30)
            j = r.json()
            print("AEMET:", r.status_code, j.get("estado"), j.get("descripcion"))
            if j.get("estado") == 200:
                g = requests.get(j["datos"], timeout=60)
                if g.content[:3] == b"GIF":
                    print("Cabeceras:", dict(g.headers))
                    return g.content, g.headers.get("Last-Modified")
                print("La descarga no era un GIF:", g.content[:60])
        except Exception as e:
            print("Error:", type(e).__name__)
        time.sleep(20)
    raise SystemExit("AEMET no devolvio el radar")


def hora_imagen(last_modified):
    # hora de la imagen segun la cabecera de descarga de AEMET (si la envia)
    if not last_modified:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(last_modified)
        return dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return None


def procesar(contenido, carpeta="radar", imagen=None):
    im = Image.open(io.BytesIO(contenido)).convert("RGB")
    mapa = im.crop((0, 0, MAPA, MAPA))
    w, h = mapa.size
    px = mapa.load()

    costa_path = os.path.join(carpeta, "costa.png")
    if os.path.exists(costa_path):
        costa = Image.open(costa_path).convert("L")
    else:
        costa = Image.new("L", (w, h), 0)
        c = costa.load()
        n = 0
        for y in range(h):
            for x in range(w):
                if px[x, y] == (255, 255, 0):
                    c[x, y] = 255
                    n += 1
        costa.save(costa_path)
        print("Plantilla de costa creada:", n, "pixeles")
    cp = costa.load()

    niv = [[None] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if cp[x, y] == 0:
                niv[y][x] = PALETA.get(px[x, y])

    # donde esta dibujada la costa no sabemos que habia debajo: miramos a los vecinos
    for y in range(h):
        for x in range(w):
            if cp[x, y] > 0:
                vec = []
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        xx, yy = x + dx, y + dy
                        if (dx or dy) and 0 <= xx < w and 0 <= yy < h and niv[yy][xx] is not None:
                            vec.append(niv[yy][xx])
                if len(vec) >= 3:
                    niv[y][x] = Counter(vec).most_common(1)[0][0]

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    cuenta = Counter()
    for y in range(h):
        for x in range(w):
            if niv[y][x] is not None:
                op[x, y] = COLORES[niv[y][x]]
                cuenta[niv[y][x]] += 1
    out.save(os.path.join(carpeta, "radar.png"))

    # para ajustar la posicion: la costa de AEMET en blanco
    vista = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    vp = vista.load()
    for y in range(h):
        for x in range(w):
            if cp[x, y] > 0:
                vp[x, y] = (255, 255, 255, 255)
    vista.save(os.path.join(carpeta, "costa_vista.png"))

    meta = {
        "actualizado": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "imagen": imagen,
        "pixeles": {"debil": cuenta[0], "moderada": cuenta[1], "fuerte": cuenta[2], "severa": cuenta[3]},
    }
    with open(os.path.join(carpeta, "meta.json"), "w") as f:
        json.dump(meta, f)
    print("Radar pintado:", meta["pixeles"])


if __name__ == "__main__":
    os.makedirs("radar", exist_ok=True)
    datos, last_modified = descargar()
    with open("radar/raw.gif", "wb") as f:
        f.write(datos)
    procesar(datos, imagen=hora_imagen(last_modified))
