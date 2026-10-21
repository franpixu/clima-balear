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

# Fuente del pie de la imagen de AEMET: 7x8 puntos, un caracter cada 9 pixeles, en magenta.
# 0,1,2,3,4,6,9 estan copiados de una imagen real; 5, 7 y 8 estan dibujados con el mismo estilo.
MAGENTA = (200, 0, 90)
GLIFOS = {
    "0": [".#####..", "#.....#.", "#.....#.", "#..#..#.", "#..#..#.", "#.....#.", "#.....#.", ".#####.."],
    "1": ["...#....", "..##....", "...#....", "...#....", "...#....", "...#....", "...#....", ".#####.."],
    "2": [".#####..", "#.....#.", "......#.", ".....#..", "..###...", ".#......", "#.......", "#######."],
    "3": ["#######.", ".....#..", "....#...", "...##...", ".....#..", "......#.", "#.....#.", ".#####.."],
    "4": [".....#..", "....##..", "...#.#..", "..#..#..", ".#...#..", "#######.", ".....#..", ".....#.."],
    "5": ["#######.", "#.......", "#.......", "######..", "......#.", "......#.", "#.....#.", ".#####.."],
    "6": ["..####..", ".#......", "#.......", "#.####..", "##....#.", "#.....#.", "#.....#.", ".#####.."],
    "7": ["#######.", "......#.", ".....#..", "....#...", "...#....", "..#.....", "..#.....", "..#....."],
    "8": [".#####..", "#.....#.", "#.....#.", ".#####..", "#.....#.", "#.....#.", "#.....#.", ".#####.."],
    "9": [".#####..", "#.....#.", "#.....#.", "#....##.", ".####.#.", "......#.", ".....#..", ".####..."],
    " ": ["........"] * 8,
}


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
                    return g.content, fecha_descarga(g.headers.get("Date"))
                print("La descarga no era un GIF:", g.content[:60])
        except Exception as e:
            print("Error:", type(e).__name__)
        time.sleep(20)
    raise SystemExit("AEMET no devolvio el radar")


def fecha_descarga(cabecera):
    try:
        return email.utils.parsedate_to_datetime(cabecera).astimezone(datetime.timezone.utc)
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc)


def _reconocer(bits):
    puntos = []
    for ch, g in GLIFOS.items():
        d = sum(a != b for fa, fb in zip(bits, g) for a, b in zip(fa, fb))
        puntos.append((d, ch))
    puntos.sort()
    if puntos[0][0] <= 10 and puntos[1][0] - puntos[0][0] >= 3:
        return puntos[0][1]
    return None


def _campo(px, x0, n):
    texto = ""
    for i in range(n):
        xs = x0 + 9 * i
        bits = ["".join("#" if px[xs + dx, y] == MAGENTA else "." for dx in range(8)) for y in range(519, 527)]
        ch = _reconocer(bits)
        if ch is None:
            return None
        texto += ch
    return texto


def hora_desde_imagen(im, descarga):
    """Lee la fecha y hora (UTC) que AEMET escribe en el pie de la imagen.
    Si algo no cuadra devuelve None y la web lo dice con honestidad."""
    try:
        px = im.load()
        dia = _campo(px, 189, 2)
        anyo_dia = _campo(px, 252, 5)
        hms = _campo(px, 306, 6)
        if None in (dia, anyo_dia, hms) or not anyo_dia.isdigit() or not hms.isdigit():
            return None
        fecha = datetime.date(2000 + int(anyo_dia[:2]), 1, 1) + datetime.timedelta(days=int(anyo_dia[2:]) - 1)
        if not dia.strip().isdigit() or int(dia) != fecha.day:
            return None
        t = datetime.datetime(fecha.year, fecha.month, fecha.day, int(hms[:2]), int(hms[2:4]), int(hms[4:]),
                              tzinfo=datetime.timezone.utc)
        edad = descarga - t
        if not (datetime.timedelta(minutes=-2) <= edad <= datetime.timedelta(hours=3)):
            return None
        return t.isoformat(timespec="seconds")
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
    datos, descarga = descargar()
    with open("radar/raw.gif", "wb") as f:
        f.write(datos)
    imagen = hora_desde_imagen(Image.open(io.BytesIO(datos)).convert("RGB"), descarga)
    print("Hora de la imagen (UTC):", imagen)
    procesar(datos, imagen=imagen)
