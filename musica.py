"""Melodía de fondo generada por código (sin derechos de autor). Se usa cuando no se sube una."""
import random
import wave

import numpy as np

SR = 48000
MAYOR = [0, 2, 4, 5, 7, 9, 11]
MENOR = [0, 2, 3, 5, 7, 8, 10]
ESTILOS = {
    "calmo":  {"prog": [0, 5, 3, 4], "penta": [0, 2, 4, 7, 9], "raiz": 57, "brillo": 0.4, "escala": MAYOR},
    "alegre": {"prog": [0, 4, 5, 3], "penta": [0, 2, 4, 7, 9], "raiz": 60, "brillo": 0.7, "escala": MAYOR},
    "epico":  {"prog": [0, 5, 2, 6], "penta": [0, 2, 3, 7, 8], "raiz": 50, "brillo": 0.5, "escala": MENOR},
}


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _tono(f, dur, brillo, ataque=0.01, caida=None):
    t = np.arange(int(SR * dur)) / SR
    onda = (np.sin(2 * np.pi * f * t) + brillo * 0.35 * np.sin(4 * np.pi * f * t)
            + brillo * 0.12 * np.sin(6 * np.pi * f * t))
    return onda * np.minimum(t / ataque, 1.0) * np.exp(-t / (caida or dur * 0.6))


def generar_melodia(destino, duracion, estilo="calmo", bpm=88, semilla=7):
    est = ESTILOS.get(estilo, ESTILOS["calmo"])
    esc = est["escala"]
    rnd = random.Random(semilla)
    pulso = 60 / bpm
    compas = pulso * 4
    total = np.zeros(int(SR * (duracion + 4)))

    def mezclar(sig, inicio, vol):
        a = int(inicio * SR)
        b = min(a + len(sig), len(total))
        if a < len(total):
            total[a:b] += sig[: b - a] * vol

    tiempo, c = 0.0, 0
    while tiempo < duracion + compas:
        g = est["prog"][c % len(est["prog"])]
        raiz = est["raiz"] + esc[g % 7]
        for d in (0, 2, 4):
            nota = est["raiz"] + esc[(g + d) % 7] + 12 * ((g + d) // 7)
            mezclar(_tono(_hz(nota), compas * 1.1, est["brillo"] * 0.5, ataque=0.3, caida=compas), tiempo, 0.10)
        for b in range(2):
            mezclar(_tono(_hz(raiz - 12), pulso * 2, 0.2, caida=pulso), tiempo + b * pulso * 2, 0.22)
        for p in range(8):
            if rnd.random() < 0.7:
                nota = est["raiz"] + 12 + rnd.choice(est["penta"]) + rnd.choice([0, 0, 12])
                mezclar(_tono(_hz(nota), pulso, est["brillo"], caida=pulso * 0.5), tiempo + p * pulso / 2, 0.09)
        tiempo += compas
        c += 1

    d = int(SR * pulso * 0.75)
    eco = np.zeros_like(total)
    eco[d:] = total[:-d] * 0.3
    total = (total + eco)[: int(SR * duracion)]
    total = total / (np.max(np.abs(total)) or 1) * 0.9
    estereo = (np.stack([total, total], axis=1) * 32767).astype(np.int16)
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(estereo.tobytes())
    return str(destino)
