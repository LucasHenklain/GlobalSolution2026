# ruff: noqa: S603, E501
"""Monta o vídeo pitch: cenas gravadas do protótipo + narração + legendas queimadas.

Uso (a partir da raiz):  python entrega/video/build_video.py [--saida entrega/video/VigIA_pitch_Grupo14.mp4]

Para cada cena do roteiro.json: os visuais (gravações de tela ou imagens reais) são ajustados para durar exatamente
o tempo da narração; depois tudo é concatenado e as legendas (ASS) são queimadas. Limite do enunciado: 3 minutos.
Adaptado do montador usado pela equipe nos projetos Startup One e AgroSmart (FIAP 2026).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import imageio_ffmpeg

AQUI = Path(__file__).resolve().parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
TRABALHO = AQUI / "_work"
PAUSA_FIM = 0.45  # respiro entre uma cena e a próxima
FUNDO = "0x0b1f33"
LIMITE_S = 175.0
CODEC = ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p"]


def rodar(comando: list[str]) -> None:
    r = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stderr[-3000:])
        raise SystemExit(f"falhou: {' '.join(map(str, comando))[:300]}")


def duracao(arquivo: Path) -> float:
    r = subprocess.run([FFMPEG, "-i", str(arquivo)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not m:
        raise SystemExit(f"sem duração: {arquivo}")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def parte_de_video(visual: dict, alvo: float, saida: Path, w: int, h: int, fps: int) -> None:
    """Estica ou comprime a gravação para durar `alvo` segundos, sem cortar conteúdo."""
    origem = AQUI / visual["video"]
    fator = alvo / duracao(origem)
    if visual.get("celular"):
        # Tela de celular: centralizada sobre fundo escuro, com a altura da tela do vídeo.
        enquadrar = f"scale=-2:{h - 40}:out_range=limited,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={FUNDO}"
    else:
        enquadrar = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease:out_range=limited,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=white"
        )
    filtro = f"setpts={fator:.5f}*PTS,{enquadrar},fps={fps},format=yuv420p"
    rodar([FFMPEG, "-y", "-i", str(origem), "-vf", filtro, "-t", f"{alvo:.3f}", "-an", "-color_range", "tv", *CODEC, str(saida)])


def parte_de_imagem(visual: dict, alvo: float, saida: Path, w: int, h: int, fps: int) -> None:
    """Imagem real (captura do Wokwi, diagrama) com aproximação lenta, para a tela não ficar parada."""
    origem = AQUI / visual["imagem"]
    quadros = int(round(alvo * fps))
    if visual.get("ajuste") == "conter":
        pre = f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=decrease,pad={w * 2}:{h * 2}:(ow-iw)/2:(oh-ih)/2:color=white"
        zoom_final, foco_x, foco_y = 1.06, "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    else:
        pre = f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2}"
        # Na captura do Wokwi o circuito fica à direita: a aproximação caminha para lá.
        zoom_final, foco_x, foco_y = 1.45, "(iw-iw/zoom)*0.92", "(ih-ih/zoom)*0.45"
    passo = (zoom_final - 1) / max(quadros, 1)
    filtro = (
        f"{pre},setsar=1,zoompan=z='min(zoom+{passo:.6f},{zoom_final})':x='{foco_x}':y='{foco_y}'"
        f":d={quadros}:s={w}x{h}:fps={fps},format=yuv420p"
    )
    rodar([FFMPEG, "-y", "-loop", "1", "-framerate", str(fps), "-i", str(origem), "-vf", filtro, "-t", f"{alvo:.3f}",
           "-r", str(fps), "-an", *CODEC, str(saida)])  # fmt: skip


def montar_cena(cena: dict, w: int, h: int, fps: int) -> tuple[Path, float, float]:
    """Devolve (clipe da cena com áudio, duração do áudio, duração total da cena)."""
    audio = AQUI / "audio" / f"{cena['id']}.mp3"
    dur_audio = duracao(audio)
    total = dur_audio + PAUSA_FIM
    pesos = [v.get("peso", 1.0) for v in cena["visuais"]]
    partes = []
    for i, (visual, peso) in enumerate(zip(cena["visuais"], pesos, strict=True)):
        alvo = total * peso / sum(pesos)
        parte = TRABALHO / f"{cena['id']}_{i}.mp4"
        (parte_de_video if "video" in visual else parte_de_imagem)(visual, alvo, parte, w, h, fps)
        partes.append(parte)
    lista = TRABALHO / f"{cena['id']}.txt"
    lista.write_text("\n".join(f"file '{p.as_posix()}'" for p in partes), encoding="utf-8")
    visual_cena = TRABALHO / f"{cena['id']}_visual.mp4"
    rodar([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(visual_cena)])
    clipe = TRABALHO / f"{cena['id']}.mp4"
    rodar([FFMPEG, "-y", "-i", str(visual_cena), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
           "-af", f"apad=whole_dur={total:.3f}", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
           "-t", f"{total:.3f}", "-c:v", "copy", str(clipe)])  # fmt: skip
    return clipe, dur_audio, total


def dividir_legenda(texto: str, maximo: int = 64) -> list[str]:
    """Quebra a narração em trechos curtos, respeitando a pontuação."""
    trechos = []
    for frase in re.split(r"(?<=[\.\!\?;])\s+", re.sub(r"\s+", " ", texto.strip())):
        if len(frase) <= maximo:
            trechos.append(frase)
            continue
        atual = ""
        for pedaco in re.split(r"(?<=,)\s+", frase):
            if len(atual) + len(pedaco) + 1 <= maximo:
                atual = (atual + " " + pedaco).strip()
            else:
                if atual:
                    trechos.append(atual)
                atual = pedaco
        trechos += textwrap.wrap(atual, maximo) if len(atual) > maximo else [atual]
    return [t for t in trechos if t]


def tempo_ass(t: float) -> str:
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def escrever_legendas(cenas: list[dict], tempos: list[tuple[float, float, float]], w: int, h: int, destino: Path) -> None:
    cabecalho = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Legenda,Segoe UI,40,&H00FFFFFF,&H000000FF,&H48101010,&H48101010,-1,0,0,0,100,100,0,0,3,10,0,2,140,140,34,1
Style: Titulo,Segoe UI,58,&H00FFFFFF,&H000000FF,&H1833200B,&H1833200B,-1,0,0,0,100,100,0,0,3,22,0,5,100,100,0,1
Style: Fonte,Segoe UI,24,&H00FFFFFF,&H000000FF,&H48101010,&H48101010,0,0,0,0,100,100,0,0,3,7,0,1,40,30,150,1
Style: Esquerda,Segoe UI,40,&H00FFFFFF,&H000000FF,&H1833200B,&H1833200B,-1,0,0,0,100,100,0,0,3,16,0,4,110,30,0,1
Style: Direita,Segoe UI,36,&H00FFFFFF,&H000000FF,&H1833200B,&H1833200B,-1,0,0,0,100,100,0,0,3,16,0,6,30,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    linhas = []
    for cena, (inicio, dur_audio, total) in zip(cenas, tempos, strict=True):
        trechos = dividir_legenda(cena["narracao"])
        letras = sum(len(t) for t in trechos)
        cursor = inicio + 0.10
        for trecho in trechos:
            d = (dur_audio - 0.10) * len(trecho) / letras
            linhas.append(f"Dialogue: 0,{tempo_ass(cursor)},{tempo_ass(cursor + d)},Legenda,,0,0,0,,{trecho}")
            cursor += d
        if cena.get("titulo"):
            a, b = cena["titulo_seg"]
            de = inicio + a if a >= 0 else inicio + total + a
            ate = inicio + b if b >= 0 else inicio + total + b
            linhas.append(f"Dialogue: 1,{tempo_ass(de)},{tempo_ass(ate)},Titulo,,0,0,0,,{cena['titulo']}")
        for nota in cena.get("notas", []):
            de, ate = tempo_ass(inicio + nota["de"]), tempo_ass(inicio + nota["ate"])
            linhas.append(f"Dialogue: 1,{de},{ate},{nota['estilo']},,0,0,0,,{nota['texto']}")
        if cena.get("fonte"):
            linhas.append(f"Dialogue: 1,{tempo_ass(inicio + 6)},{tempo_ass(inicio + total)},Fonte,,0,0,0,,{cena['fonte']}")
    destino.write_text(cabecalho + "\n".join(linhas) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", type=Path, default=AQUI / "VigIA_pitch_Grupo14.mp4")
    args = ap.parse_args()
    roteiro = json.loads((AQUI / "roteiro.json").read_text(encoding="utf-8"))
    w, h, fps = roteiro["largura"], roteiro["altura"], roteiro["fps"]
    shutil.rmtree(TRABALHO, ignore_errors=True)
    TRABALHO.mkdir()
    clipes, tempos, t = [], [], 0.0
    for cena in roteiro["cenas"]:
        clipe, dur_audio, total = montar_cena(cena, w, h, fps)
        clipes.append(clipe)
        tempos.append((t, dur_audio, total))
        print(f"{cena['id']}: {tempo_ass(t)} + {total:.1f} s")
        t += total
    if t > LIMITE_S:
        raise SystemExit(f"vídeo com {t:.1f} s: passa do limite de {LIMITE_S:.0f} s. Encurte a narração.")
    lista = TRABALHO / "lista.txt"
    lista.write_text("\n".join(f"file '{c.as_posix()}'" for c in clipes), encoding="utf-8")
    junto = TRABALHO / "junto.mp4"
    rodar([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(junto)])
    legendas = TRABALHO / "legendas.ass"
    escrever_legendas(roteiro["cenas"], tempos, w, h, legendas)
    caminho_ass = str(legendas.resolve()).replace("\\", "/").replace(":", "\\:")
    rodar([FFMPEG, "-y", "-i", str(junto), "-vf", f"ass='{caminho_ass}'", "-c:v", "libx264", "-preset", "medium",
           "-crf", "21", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-c:a", "copy", str(args.saida)])  # fmt: skip
    print(f"OK -> {args.saida} · {t:.1f} s ({int(t // 60)}:{t % 60:04.1f}) · {args.saida.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
