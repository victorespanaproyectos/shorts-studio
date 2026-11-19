"""Motor de render: imagen + animación + música + narración opcional + subtítulos → MP4 vertical."""
import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from musica import generar_melodia

ANIMACIONES = ["ken_burns", "zoom_in", "zoom_out", "pan_izquierda", "pan_derecha",
               "pan_arriba", "pan_abajo", "pulso", "ninguna"]
INICIO_VOZ = 0.6     # segundos antes de que empiece a hablar
COLA_VOZ = 1.6       # segundos después de que termina de hablar


@dataclass
class Opciones:
    imagen: str
    salida: str = "short.mp4"
    musica: Optional[str] = None            # None → se genera una melodía
    estilo_musica: str = "calmo"
    volumen_musica: float = 0.8             # relativo; con narración baja sola cuando hay voz
    # Narración: texto (Edge-TTS) o archivo propio
    narracion_texto: str = ""
    voz: str = "Valentina (Uruguay)"
    velocidad_voz: int = 0                  # -50..+50 (%)
    narracion_archivo: Optional[str] = None
    subtitulos: bool = True
    # Video
    duracion: float = 15.0                  # se usa si no hay narración
    fps: int = 30
    resolucion: tuple = (1080, 1920)
    ajuste: str = "blur"                    # blur | cover
    animacion: str = "ken_burns"
    intensidad: float = 0.15
    titulo: str = ""
    fundido_entrada: float = 0.5
    fundido_salida: float = 0.8
    color_resaltado: str = "#FFD400"


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def duracion_audio(ruta):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "json", ruta], capture_output=True, text=True, check=True)
    return float(json.loads(out.stdout)["format"]["duration"])


def fuente(tam):
    for c in ["C:/Windows/Fonts/arialbd.ttf", "/mnt/c/Windows/Fonts/arialbd.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]:
        try:
            return ImageFont.truetype(c, tam)
        except OSError:
            continue
    return ImageFont.load_default(size=tam)


def color_a_hex(c, defecto="#FFD400"):
    """Acepta '#RRGGBB', 'rgb(...)' o 'rgba(...)' (lo que devuelva el selector de color)."""
    c = (c or "").strip()
    if c.startswith("#"):
        return c[:7]
    if c.startswith("rgb"):
        try:
            nums = [float(x) for x in c[c.index("(") + 1:c.index(")")].split(",")[:3]]
            return "#%02X%02X%02X" % tuple(int(round(n)) for n in nums)
        except ValueError:
            pass
    return defecto


def ease(t):
    return 0.5 - 0.5 * math.cos(math.pi * t)


def camara(tipo, t, k):
    if tipo == "zoom_in":
        return 1 + k * t, 0, 0
    if tipo == "zoom_out":
        return 1 + k * (1 - t), 0, 0
    if tipo.startswith("pan_"):
        s = 2 * t - 1
        dx = {"pan_izquierda": s, "pan_derecha": -s}.get(tipo, 0)
        dy = {"pan_arriba": s, "pan_abajo": -s}.get(tipo, 0)
        return 1 + k, dx, dy
    if tipo == "ken_burns":
        return 1 + k * t, 0.6 * (2 * t - 1), -0.4 * (2 * t - 1)
    if tipo == "pulso":
        return 1 + k * 0.25 * (1 - math.cos(4 * math.pi * t)) + k * 0.3 * t, 0, 0
    return 1.0, 0, 0


def preparar_lienzo(img, W, H, ajuste, margen):
    LW, LH = int(W * margen), int(H * margen)
    esc_c = max(LW / img.width, LH / img.height)
    cubre = img.resize((math.ceil(img.width * esc_c), math.ceil(img.height * esc_c)), Image.LANCZOS)
    x, y = (cubre.width - LW) // 2, (cubre.height - LH) // 2
    cubre = cubre.crop((x, y, x + LW, y + LH))
    if ajuste == "cover":
        return cubre
    fondo = cubre.filter(ImageFilter.GaussianBlur(45))
    fondo = Image.blend(fondo, Image.new("RGB", fondo.size, (0, 0, 0)), 0.35)
    esc = min(LW / img.width, LH / img.height)
    frente = img.resize((round(img.width * esc), round(img.height * esc)), Image.LANCZOS)
    # sombra suave detrás de la imagen
    sombra = Image.new("L", fondo.size, 0)
    ox, oy = (LW - frente.width) // 2, (LH - frente.height) // 2
    ImageDraw.Draw(sombra).rectangle((ox, oy + 12, ox + frente.width, oy + frente.height + 12), fill=160)
    sombra = sombra.filter(ImageFilter.GaussianBlur(25))
    fondo.paste(Image.new("RGB", fondo.size, (0, 0, 0)), (0, 0), sombra)
    fondo.paste(frente, (ox, oy))
    return fondo


# ----------------------------------------------------------------------------
# Texto: título fijo y subtítulos palabra por palabra
# ----------------------------------------------------------------------------
def envolver(draw, texto, f, max_ancho):
    lineas, actual = [], ""
    for p in texto.split():
        prueba = f"{actual} {p}".strip()
        if draw.textlength(prueba, font=f) <= max_ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def capa_titulo(texto, W, H):
    if not texto.strip():
        return None
    f = fuente(70)
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    lineas = envolver(d, texto.strip(), f, W * 0.84)
    alto = 88
    y0 = int(H * 0.11)
    for i, l in enumerate(lineas):
        w = d.textlength(l, font=f)
        d.text(((W - w) / 2, y0 + i * alto), l, font=f, fill="white", stroke_width=5, stroke_fill="black")
    return capa


def agrupar(palabras, max_palabras=3, max_chars=18):
    """Agrupa palabras en bloques cortos (estilo TikTok/Shorts), cortando en signos de puntuación."""
    grupos, actual = [], []
    for p in palabras:
        actual.append(p)
        largo = sum(len(x.texto) + 1 for x in actual)
        if len(actual) >= max_palabras or largo >= max_chars or p.texto[-1:] in ".,;:!?…":
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    return grupos


class Subtitulos:
    def __init__(self, palabras, desfase, W, H, color_resaltado):
        self.W, self.H = W, H
        self.grupos = agrupar(palabras)
        self.f = fuente(84)
        self.color = color_a_hex(color_resaltado)
        self.cache = {}
        # cada grupo se ve desde su primera palabra hasta que empieza el siguiente
        self.tramos = []
        for i, g in enumerate(self.grupos):
            ini = g[0].inicio + desfase
            fin = (self.grupos[i + 1][0].inicio + desfase) if i + 1 < len(self.grupos) else g[-1].fin + desfase + 0.4
            self.tramos.append((ini, fin))
        self.desfase = desfase

    def capa(self, seg):
        for gi, (ini, fin) in enumerate(self.tramos):
            if ini <= seg < fin:
                break
        else:
            return None
        g = self.grupos[gi]
        activa = 0
        for wi, p in enumerate(g):
            if seg >= p.inicio + self.desfase:
                activa = wi
        pop = min((seg - ini) / 0.12, 1.0)
        escala = round(0.82 + 0.18 * (1 - (1 - pop) ** 2), 2)
        clave = (gi, activa, escala)
        if clave not in self.cache:
            self.cache[clave] = self._dibujar(g, activa, escala)
        return self.cache[clave]

    def _dibujar(self, grupo, activa, escala):
        W, H = self.W, self.H
        base = Image.new("RGBA", (W, 400), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        textos = [p.texto.upper() for p in grupo]
        esp = d.textlength(" ", font=self.f)
        anchos = [d.textlength(t, font=self.f) for t in textos]
        # si no entra en una línea, dividir en dos
        lineas = [list(range(len(textos)))]
        if sum(anchos) + esp * (len(textos) - 1) > W * 0.88 and len(textos) > 1:
            m = math.ceil(len(textos) / 2)
            lineas = [list(range(m)), list(range(m, len(textos)))]
        alto = 104
        y0 = (400 - alto * len(lineas)) // 2
        for li, idxs in enumerate(lineas):
            total = sum(anchos[i] for i in idxs) + esp * (len(idxs) - 1)
            x = (W - total) / 2
            for i in idxs:
                color = self.color if i == activa else "white"
                d.text((x, y0 + li * alto), textos[i], font=self.f, fill=color,
                       stroke_width=7, stroke_fill="black")
                x += anchos[i] + esp
        if escala != 1.0:
            nw, nh = int(W * escala), int(400 * escala)
            chico = base.resize((nw, nh), Image.LANCZOS)
            base = Image.new("RGBA", (W, 400), (0, 0, 0, 0))
            base.paste(chico, ((W - nw) // 2, (400 - nh) // 2))
        capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        capa.paste(base, (0, int(H * 0.60) - 200))   # zona segura de Shorts (lejos de botones)
        return capa


# ----------------------------------------------------------------------------
# Cuadros
# ----------------------------------------------------------------------------
def generar_cuadros(op: Opciones, dur, subs: Optional[Subtitulos]):
    W, H = op.resolucion
    k = float(op.intensidad)
    margen = 1 + k + 0.02
    lienzo = preparar_lienzo(Image.open(op.imagen).convert("RGB"), W, H, op.ajuste, margen)
    LW, LH = lienzo.size
    titulo = capa_titulo(op.titulo, W, H)
    n = int(round(dur * op.fps))
    for i in range(n):
        seg = i / op.fps
        zoom, dx, dy = camara(op.animacion, ease(i / max(n - 1, 1)), k)
        vw, vh = min(W * margen / zoom, LW), min(H * margen / zoom, LH)
        cx = LW / 2 + dx * (LW - vw) / 2
        cy = LH / 2 + dy * (LH - vh) / 2
        cuadro = lienzo.resize((W, H), Image.BICUBIC, box=(cx - vw / 2, cy - vh / 2, cx + vw / 2, cy + vh / 2))
        if titulo is not None:
            cuadro.paste(titulo, (0, 0), titulo)
        if subs is not None:
            capa = subs.capa(seg)
            if capa is not None:
                cuadro.paste(capa, (0, 0), capa)
        brillo = 1.0
        if op.fundido_entrada > 0 and seg < op.fundido_entrada:
            brillo = seg / op.fundido_entrada
        if op.fundido_salida > 0 and seg > dur - op.fundido_salida:
            brillo = min(brillo, max((dur - seg) / op.fundido_salida, 0))
        arr = np.asarray(cuadro)
        if brillo < 1:
            arr = (arr * brillo).astype(np.uint8)
        yield arr.tobytes()


# ----------------------------------------------------------------------------
# Render
# ----------------------------------------------------------------------------
def render(op: Opciones, progreso: Callable[[float, str], None] = lambda p, m: None,
           sintetizador=None):
    """Genera el Short. `sintetizador` permite inyectar otro TTS (se usa en tests)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("No se encontró ffmpeg. Instalalo: sudo apt install ffmpeg")
    W, H = op.resolucion

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        voz, palabras = None, []

        # 1) Narración
        if op.narracion_archivo:
            voz = op.narracion_archivo
        elif op.narracion_texto.strip():
            progreso(0.02, "Generando narración…")
            if sintetizador is None:
                from narracion import sintetizar as sintetizador
            voz = str(tmp / "voz.mp3")
            palabras = sintetizador(op.narracion_texto.strip(), op.voz, voz, op.velocidad_voz)

        # 2) Duración
        dur = float(op.duracion)
        if voz:
            dur = INICIO_VOZ + duracion_audio(voz) + COLA_VOZ
        dur = min(dur, 180.0)  # límite de Shorts

        # 3) Música
        musica = op.musica
        if not musica:
            progreso(0.06, "Generando melodía…")
            musica = generar_melodia(tmp / "musica.wav", dur, op.estilo_musica)

        subs = Subtitulos(palabras, INICIO_VOZ, W, H, op.color_resaltado) if (palabras and op.subtitulos) else None

        # 4) Mezcla de audio
        fade_out = max(dur - 2.0, 0)
        m = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={op.volumen_musica},"
             f"afade=t=in:st=0:d=1,afade=t=out:st={fade_out}:d=2[m]")
        if voz:
            ms = int(INICIO_VOZ * 1000)
            filtro = (m + f";[2:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}:all=1,apad[v];"
                      "[v]asplit=2[v1][v2];"
                      # ducking: la música baja sola cuando hay voz
                      "[m][v1]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400[md];"
                      "[md][v2]amix=inputs=2:duration=first:normalize=0,"
                      "loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        else:
            filtro = m + ";[m]loudnorm=I=-14:TP=-1.5:LRA=11[a]"

        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(op.fps), "-i", "-",
               "-stream_loop", "-1", "-i", musica]
        if voz:
            cmd += ["-i", voz]
        cmd += ["-filter_complex", filtro, "-map", "0:v", "-map", "[a]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-t", f"{dur:.3f}", "-movflags", "+faststart", op.salida]

        # 5) Render de cuadros → ffmpeg
        total = int(round(dur * op.fps))
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for i, cuadro in enumerate(generar_cuadros(op, dur, subs), 1):
                proc.stdin.write(cuadro)
                if i % op.fps == 0:
                    progreso(0.1 + 0.85 * i / total, f"Renderizando {i}/{total} cuadros")
        except BrokenPipeError:
            pass
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="ignore")
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg falló: {err[-800:]}")
    progreso(1.0, "Listo")
    return op.salida, dur
