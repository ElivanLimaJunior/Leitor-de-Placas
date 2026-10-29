"""Etapa 6: processa um vídeo inteiro e gera um registro por veículo."""

import argparse
import sys
from collections import Counter
from pathlib import Path

import cv2

from leitor.deteccao import DetectorDePlacas, recortar
from leitor.medicao import ler_gabarito
from leitor.ocr import VERMELHO, LeitorDePlacas
from leitor.rastreamento import Observacao, Rastreador, Registro
from leitor.video import TECLA_ESC, desenhar_caixa, escrever_info, redimensionar

# Quanto tempo uma placa pode sumir (encoberta, fora do quadro) antes de o veículo ser dado como saído.
AUSENCIA_MAXIMA_S = 1.0
# Se a mesma placa voltar até este tempo depois, é a mesma passagem.
JANELA_JUNCAO_S = 5.0


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
    args = parser.parse_args()

    captura = cv2.VideoCapture(args.video)
    if not captura.isOpened():
        print(f"Não foi possível abrir o vídeo: {args.video}", file=sys.stderr)
        return 1
    fps = captura.get(cv2.CAP_PROP_FPS) or 30
    total = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))

    detector = DetectorDePlacas()
    leitor = LeitorDePlacas()
    rastreador = Rastreador(ausencia_maxima=int(AUSENCIA_MAXIMA_S * fps), janela_juncao=int(JANELA_JUNCAO_S * fps))

    def anunciar(novos: list[Registro]) -> None:
        for r in novos:
            print(f"\r[{formatar_tempo(r.primeiro_quadro, fps)}] registro {len(rastreador.registros)}: {r.placa}   ")

    numero = -1
    while True:
        ok, quadro = captura.read()
        if not ok:
            break
        numero += 1
        if numero % args.passo:
            continue

        observacoes = []
        for d in detector.detectar(quadro):
            leitura = leitor.ler(recortar(quadro, d))
            observacoes.append(Observacao(d.x1, d.y1, d.x2, d.y2, leitura.placa, leitura.confianca))
        anunciar(rastreador.atualizar(numero, observacoes))

        if args.sem_janela:
            print(f"\rquadro {numero}/{total}", end="", flush=True)
            continue

        for t in rastreador.trilhas:
            if t.ultimo_quadro != numero:
                continue  # veículo não visto neste quadro
            o = t.ultima
            if t.placa:
                desenhar_caixa(quadro, o.x1, o.y1, o.x2, o.y2, f"#{t.numero} {t.placa}")
            else:
                cv2.rectangle(quadro, (o.x1, o.y1), (o.x2, o.y2), VERMELHO, 2)
        quadro = redimensionar(quadro, args.largura)
        escrever_info(quadro, f"quadro {numero}/{total} | registros: {len(rastreador.registros)} | q/Esc: sair")
        cv2.imshow("Leitor de Placas", quadro)
        if (cv2.waitKey(1) & 0xFF) in (ord("q"), TECLA_ESC):
            break

    anunciar(rastreador.finalizar())
    captura.release()
    cv2.destroyAllWindows()

    print(f"\n{len(rastreador.registros)} registro(s):")
    for i, r in enumerate(rastreador.registros, 1):
        votos = ", ".join(f"{p}={v:.1f}" for p, v in sorted(r.votos.items(), key=lambda kv: -kv[1]))
        print(
            f"  {i:2d}. {r.placa}  de {formatar_tempo(r.primeiro_quadro, fps)} a {formatar_tempo(r.ultimo_quadro, fps)}"
            f"  votos: {votos}"
        )

    if args.gabarito:
        comparar_com_gabarito(rastreador.registros, ler_gabarito(Path(args.gabarito)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
