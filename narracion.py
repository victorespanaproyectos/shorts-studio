"""Narración con Edge-TTS (voces neuronales de Microsoft, gratis, requiere internet).

Devuelve el audio y los tiempos de cada palabra, que se usan para los subtítulos.
"""
import asyncio
import re
from dataclasses import dataclass

import edge_tts

# Voces recomendadas (se puede escribir cualquier otra voz de `edge-tts --list-voices`)
VOCES = {
    "Valentina (Uruguay)": "es-UY-ValentinaNeural",
    "Mateo (Uruguay)": "es-UY-MateoNeural",
    "Elena (Argentina)": "es-AR-ElenaNeural",
    "Tomás (Argentina)": "es-AR-TomasNeural",
    "Dalia (México)": "es-MX-DaliaNeural",
    "Jorge (México)": "es-MX-JorgeNeural",
    "Salomé (Colombia)": "es-CO-SalomeNeural",
    "Gonzalo (Colombia)": "es-CO-GonzaloNeural",
    "Elvira (España)": "es-ES-ElviraNeural",
    "Álvaro (España)": "es-ES-AlvaroNeural",
    "Ava (Inglés EE.UU.)": "en-US-AvaNeural",
    "Andrew (Inglés EE.UU.)": "en-US-AndrewNeural",
}


@dataclass
class Palabra:
    inicio: float  # segundos
    fin: float
    texto: str


def _norm(s):
    return re.sub(r"[^\wáéíóúüñ]", "", s.lower())


def _restaurar_puntuacion(palabras, texto_original):
    """Edge-TTS devuelve palabras sin signos; las alineamos con el texto original
    para que los subtítulos muestren comas, signos de pregunta, etc."""
    tokens = texto_original.split()
    j = 0
    for p in palabras:
        objetivo = _norm(p.texto)
        for k in range(j, min(j + 4, len(tokens))):
            if objetivo and objetivo in _norm(tokens[k]):
                p.texto = tokens[k]
                j = k + 1
                break
    return palabras


async def _sintetizar(texto, voz, velocidad, destino):
    rate = f"{velocidad:+d}%"
    com = edge_tts.Communicate(texto, voz, rate=rate, boundary="WordBoundary")
    palabras = []
    with open(destino, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                ini = chunk["offset"] / 1e7          # unidades de 100 ns → segundos
                palabras.append(Palabra(ini, ini + chunk["duration"] / 1e7, chunk["text"]))
    return palabras


def sintetizar(texto, voz, destino, velocidad=0):
    """Genera `destino` (mp3) y devuelve la lista de Palabra con sus tiempos."""
    voz = VOCES.get(voz, voz)
    try:
        palabras = asyncio.run(_sintetizar(texto, voz, int(velocidad), destino))
    except Exception as e:  # sin internet, voz inexistente, etc.
        raise RuntimeError(f"No se pudo generar la narración con Edge-TTS ({e}). "
                           "Revisá la conexión a internet y el nombre de la voz.") from e
    return _restaurar_puntuacion(palabras, texto)
