"""Etapa 3: encontrar placas numa imagem com um modelo YOLO em ONNX (open-image-models)."""

import argparse
import sys
from dataclasses import dataclass

import cv2
import numpy as np
from open_image_models import create_detector

from leitor.video import desenhar_caixa, escrever_info, redimensionar

# Modelo sugerido na documentação da open-image-models: pequeno e rápido no processador.
MODELO_PADRAO = "yolo-v9-t-384-license-plate-end2end"

# Limite provisório. O valor definitivo será escolhido na Etapa 5, medindo.
CONFIANCA_MINIMA = 0.25


@dataclass
class Deteccao:
    """Uma placa encontrada: caixa delimitadora (x1, y1, x2, y2) e confiança de 0 a 1."""

    x1: int
    y1: int
    x2: int
    y2: int
    confianca: float


class DetectorDePlacas:
    """Envolve o detector da open-image-models para o resto do projeto não depender da biblioteca."""

    def __init__(self, modelo: str = MODELO_PADRAO, confianca_minima: float = CONFIANCA_MINIMA):
        # Só CPU: o projeto precisa rodar em qualquer computador, sem placa de vídeo.
        self._detector = create_detector(
            modelo, conf_thresh=confianca_minima, providers=["CPUExecutionProvider"]
        )

    def detectar(self, imagem: np.ndarray) -> list[Deteccao]:
        """Devolve as placas encontradas na imagem (BGR), da mais confiável para a menos."""
        resultados = self._detector.predict(imagem)
        deteccoes = [
            Deteccao(r.bounding_box.x1, r.bounding_box.y1, r.bounding_box.x2, r.bounding_box.y2, r.confidence)
            for r in resultados
        ]
        return sorted(deteccoes, key=lambda d: d.confianca, reverse=True)


def recortar(imagem: np.ndarray, deteccao: Deteccao) -> np.ndarray:
    """Recorta a região da placa, limitando a caixa às bordas da imagem."""
    altura, largura = imagem.shape[:2]
    x1, y1 = max(deteccao.x1, 0), max(deteccao.y1, 0)
    x2, y2 = min(deteccao.x2, largura), min(deteccao.y2, altura)
    return imagem[y1:y2, x1:x2]


def ler_imagem(caminho: str, quadro: int) -> np.ndarray | None:
    """Abre uma foto ou, se for vídeo, pega o quadro de número `quadro`."""
    imagem = cv2.imread(caminho)
    if imagem is not None:
        return imagem
    captura = cv2.VideoCapture(caminho)
    captura.set(cv2.CAP_PROP_POS_FRAMES, quadro)
    ok, imagem = captura.read()
    captura.release()
    return imagem if ok else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Marca as placas encontradas numa foto (ou num quadro de vídeo).")
    parser.add_argument("arquivo", help="foto (.jpg, .png) ou vídeo")
    parser.add_argument("--quadro", type=int, default=0, help="número do quadro, se o arquivo for vídeo (padrão: 0)")
    parser.add_argument("--salvar", help="salva a imagem marcada neste caminho em vez de abrir a janela")
    parser.add_argument("--largura", type=int, default=1280, help="largura máxima da janela (padrão: 1280)")
    args = parser.parse_args()

    imagem = ler_imagem(args.arquivo, args.quadro)
    if imagem is None:
        print(f"Não foi possível abrir: {args.arquivo}", file=sys.stderr)
        return 1

    deteccoes = DetectorDePlacas().detectar(imagem)
    print(f"{len(deteccoes)} placa(s) encontrada(s)")
    for d in deteccoes:
        print(f"  caixa=({d.x1}, {d.y1}, {d.x2}, {d.y2})  confiança={d.confianca:.2f}")
        desenhar_caixa(imagem, d.x1, d.y1, d.x2, d.y2, f"placa {d.confianca:.0%}")

    if args.salvar:
        cv2.imwrite(args.salvar, imagem)
        print(f"Imagem salva em {args.salvar}")
        return 0

    imagem = redimensionar(imagem, args.largura)
    escrever_info(imagem, f"{len(deteccoes)} placa(s) | qualquer tecla: sair")
    cv2.imshow("Leitor de Placas", imagem)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
