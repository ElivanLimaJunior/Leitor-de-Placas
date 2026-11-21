"""Etapa 6: processa um vídeo inteiro e gera um registro por veículo.

O trabalho de cada quadro (detecção, OCR, rastreamento e regras) fica em leitor.motor,
o mesmo usado pelo painel web.
"""

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2

from leitor import config as cfg
from leitor.banco import FORMATO_DATA, Banco
from leitor.estacionamento import Estacionamento
from leitor.medicao import ler_gabarito
from leitor.motor import ENTRADA, SAIDA, Motor
from leitor.rastreamento import Registro
from leitor.video import TECLA_ESC, escrever_info, redimensionar


def formatar_tempo(quadro: int, fps: float) -> str:
    segundos = quadro / fps
    return f"{int(segundos // 60):02d}:{segundos % 60:05.2f}"


def comparar_com_gabarito(registros: list[Registro], gabarito: set[str]) -> None:
    contagem = Counter(r.placa for r in registros)
    certas = {p for p in contagem if p in gabarito}
    erradas = {p: n for p, n in contagem.items() if p not in gabarito}
    duplicadas = {p: n for p, n in contagem.items() if p in gabarito and n > 1}
    faltando = gabarito - certas

    print(f"\nComparação com o gabarito ({len(gabarito)} placas):")
    print(f"  {len(registros)} registros; {len(certas)} placas certas")
    print(f"  duplicados (mesmo carro registrado mais de uma vez): {duplicadas or 'nenhum'}")
    print(f"  errados (placa fora do gabarito): {erradas or 'nenhum'}")
    print(f"  faltando: {sorted(faltando) or 'nenhuma'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Processa um vídeo e gera um registro por veículo.")
    parser.add_argument("video")
    parser.add_argument("--passo", type=int, default=3, help="analisa 1 a cada N quadros (padrão: 3)")
    parser.add_argument("--sem-janela", action="store_true", help="não mostra o vídeo (mais rápido)")
    parser.add_argument("--gabarito", help="planilha com as placas certas, para comparar no final")
    parser.add_argument("--largura", type=int, default=1280, help="largura máxima da janela (padrão: 1280)")
    parser.add_argument("--banco", help="grava os registros neste banco SQLite (ex.: data/estacionamento.db)")
    parser.add_argument(
        "--camera", choices=[ENTRADA, SAIDA], default=ENTRADA, help="o que a câmera filma (padrão: entrada)"
    )
    parser.add_argument(
        "--inicio", help="data e hora do começo do vídeo, AAAA-MM-DD HH:MM:SS (padrão: agora)"
    )
    args = parser.parse_args()

    captura = cv2.VideoCapture(args.video)
    if not captura.isOpened():
        print(f"Não foi possível abrir o vídeo: {args.video}", file=sys.stderr)
        return 1
    fps = captura.get(cv2.CAP_PROP_FPS) or 30
    total = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))

    banco = Banco(args.banco) if args.banco else None
    estacionamento = Estacionamento(banco, cfg.carregar()) if banco else None
    inicio = datetime.strptime(args.inicio, FORMATO_DATA) if args.inicio else datetime.now()
    motor = Motor(fps, estacionamento, args.camera, inicio)

    def anunciar(eventos) -> None:
        for e in eventos:
            print(f"\r{e.hora}  {e.mensagem}   ")

    numero = -1
    while True:
        ok, quadro = captura.read()
        if not ok:
            break
        numero += 1
        if numero % args.passo:
            continue

        anunciar(motor.processar(numero, quadro))

        if args.sem_janela:
            print(f"\rquadro {numero}/{total}", end="", flush=True)
            continue
        quadro = redimensionar(quadro, args.largura)
        registros = len(motor.rastreador.registros)
        escrever_info(quadro, f"quadro {numero}/{total} | registros: {registros} | q/Esc: sair")
        cv2.imshow("Leitor de Placas", quadro)
        if (cv2.waitKey(1) & 0xFF) in (ord("q"), TECLA_ESC):
            break

    anunciar(motor.finalizar())
    captura.release()
    cv2.destroyAllWindows()
    if banco:
        banco.fechar()

    registros = motor.rastreador.registros
    print(f"\n{len(registros)} registro(s):")
    for i, r in enumerate(registros, 1):
        votos = ", ".join(f"{p}={v:.1f}" for p, v in sorted(r.votos.items(), key=lambda kv: -kv[1]))
        print(
            f"  {i:2d}. {r.placa}  de {formatar_tempo(r.primeiro_quadro, fps)} a {formatar_tempo(r.ultimo_quadro, fps)}"
            f"  votos: {votos}"
        )

    if args.gabarito:
        comparar_com_gabarito(registros, ler_gabarito(Path(args.gabarito)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
