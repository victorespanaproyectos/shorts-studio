"""Shorts Studio — interfaz web local.

Ejecutar:  python app.py   → abrir http://localhost:7860
"""
import time
from pathlib import Path

import gradio as gr

from motor import ANIMACIONES, Opciones, render
from narracion import VOCES

SALIDAS = Path(__file__).parent / "salidas"
SALIDAS.mkdir(exist_ok=True)

NOMBRES_ANIM = {
    "Ken Burns (zoom + paneo)": "ken_burns", "Zoom de acercamiento": "zoom_in",
    "Zoom de alejamiento": "zoom_out", "Paneo a la izquierda": "pan_izquierda",
    "Paneo a la derecha": "pan_derecha", "Paneo hacia arriba": "pan_arriba",
    "Paneo hacia abajo": "pan_abajo", "Pulso": "pulso", "Sin movimiento": "ninguna",
}
assert set(NOMBRES_ANIM.values()) == set(ANIMACIONES)

SIN_NARR, VOZ_AUTO, VOZ_PROPIA = "Sin narración", "Voz automática (escribo el texto)", "Subo mi propia grabación"


def generar(imagen, musica, estilo_musica, volumen, modo, texto, voz, velocidad, grabacion,
            subtitulos, color, animacion, intensidad, ajuste, titulo, duracion, fps,
            progress=gr.Progress()):
    if not imagen:
        raise gr.Error("Subí una imagen.")
    if modo == VOZ_AUTO and not (texto or "").strip():
        raise gr.Error("Escribí el texto que querés que se narre.")
    if modo == VOZ_PROPIA and not grabacion:
        raise gr.Error("Subí tu grabación de narración.")

    salida = SALIDAS / f"short_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    op = Opciones(
        imagen=imagen, salida=str(salida),
        musica=musica or None, estilo_musica=estilo_musica, volumen_musica=volumen,
        narracion_texto=texto if modo == VOZ_AUTO else "",
        voz=voz, velocidad_voz=int(velocidad),
        narracion_archivo=grabacion if modo == VOZ_PROPIA else None,
        subtitulos=subtitulos, color_resaltado=color,
        animacion=NOMBRES_ANIM[animacion], intensidad=intensidad, ajuste=ajuste,
        titulo=titulo or "", duracion=duracion, fps=int(fps),
    )
    try:
        _, dur = render(op, progreso=lambda p, m: progress(p, desc=m))
    except RuntimeError as e:
        raise gr.Error(str(e))
    return str(salida), str(salida), f"✅ Short generado: {dur:.1f} s · {salida.name}"


with gr.Blocks(title="Shorts Studio") as demo:
    gr.Markdown("# 🎬 Shorts Studio\nSubí una imagen y una melodía, elegí si querés narración y generá tu YouTube Short (1080×1920).")
    with gr.Row():
        with gr.Column(scale=1):
            imagen = gr.Image(label="1. Imagen", type="filepath", height=320)
            musica = gr.Audio(label="2. Melodía (opcional: si no subís, se genera una)", type="filepath",
                              sources=["upload"])
            with gr.Row():
                estilo_musica = gr.Dropdown(["calmo", "alegre", "epico"], value="calmo",
                                            label="Estilo de melodía generada")
                volumen = gr.Slider(0.1, 1.0, value=0.7, step=0.05, label="Volumen de la música")

            gr.Markdown("### 3. Narración")
            modo = gr.Radio([SIN_NARR, VOZ_AUTO, VOZ_PROPIA], value=SIN_NARR, show_label=False)
            with gr.Group(visible=False) as grupo_auto:
                texto = gr.Textbox(label="Texto a narrar", lines=4,
                                   placeholder="¿Sabías que…? Escribí acá lo que querés que diga la voz.")
                with gr.Row():
                    voz = gr.Dropdown(list(VOCES), value="Valentina (Uruguay)", label="Voz",
                                      allow_custom_value=True)
                    velocidad = gr.Slider(-30, 30, value=0, step=5, label="Velocidad (%)")
                with gr.Row():
                    subtitulos = gr.Checkbox(value=True, label="Subtítulos animados")
                    color = gr.ColorPicker(value="#FFD400", label="Color palabra activa")
            grabacion = gr.Audio(label="Tu grabación", type="filepath", sources=["upload", "microphone"],
                                 visible=False)

            with gr.Accordion("4. Imagen y animación", open=False):
                animacion = gr.Dropdown(list(NOMBRES_ANIM), value="Ken Burns (zoom + paneo)", label="Animación")
                intensidad = gr.Slider(0.05, 0.4, value=0.15, step=0.01, label="Intensidad del movimiento")
                ajuste = gr.Radio([("Imagen completa + fondo desenfocado", "blur"),
                                   ("Recortar para llenar la pantalla", "cover")], value="blur", label="Ajuste")
                titulo = gr.Textbox(label="Título fijo arriba (opcional)")
            with gr.Accordion("5. Duración y calidad", open=False):
                duracion = gr.Slider(5, 60, value=15, step=1,
                                     label="Duración en segundos (si hay narración, se ajusta sola)")
                fps = gr.Radio(["30", "60"], value="30", label="FPS")

            boton = gr.Button("Generar Short", variant="primary", size="lg")

        with gr.Column(scale=1):
            video = gr.Video(label="Resultado", height=640)
            estado = gr.Markdown()
            archivo = gr.File(label="Descargar MP4")

    def cambiar_modo(m):
        return gr.update(visible=m == VOZ_AUTO), gr.update(visible=m == VOZ_PROPIA)

    modo.change(cambiar_modo, modo, [grupo_auto, grabacion])
    boton.click(generar,
                [imagen, musica, estilo_musica, volumen, modo, texto, voz, velocidad, grabacion,
                 subtitulos, color, animacion, intensidad, ajuste, titulo, duracion, fps],
                [video, archivo, estado])

if __name__ == "__main__":
    demo.queue().launch(theme=gr.themes.Soft(), inbrowser=True)
