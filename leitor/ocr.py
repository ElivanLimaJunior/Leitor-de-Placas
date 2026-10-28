"""Etapa 4: ler os caracteres da placa (OCR) com a fast-plate-ocr e validar pelas regras da etapa 2."""

import argparse
import sys
from dataclasses import dataclass

import cv2
import numpy as np
from fast_plate_ocr import LicensePlateRecognizer

from leitor.deteccao import DetectorDePlacas, ler_imagem, recortar
from leitor.placa import corrigir_placa, formato_placa, normalizar
from leitor.video import desenhar_caixa, escrever_info, redimensionar

# Modelo recomendado na documentação da fast-plate-ocr, treinado com placas de vários países (inclui o Brasil).
MODELO_PADRAO = "cct-s-v2-global-model"

VERMELHO = (0, 0, 255)


@dataclass
class Leitura:
    """Resultado do OCR de um recorte de placa."""

    texto_bruto: str
    """O que o OCR leu, sem nenhuma correção."""
    confiancas: list[float]
    """Confiança de 0 a 1 de cada caractere lido."""
    placa: str | None
    """Placa corrigida e válida, ou None se o texto não virou placa brasileira."""
    formato: str | None
    """"antigo", "mercosul" ou None."""

    @property
    def confianca(self) -> float:
        """Confiança da leitura inteira: a do caractere mais fraco, pois basta um errado para errar a placa."""
        return min(self.confiancas, default=0.0)


def interpretar(texto_bruto: str, confiancas: list[float]) -> Leitura:
    """Aplica as regras da placa brasileira (etapa 2) ao texto vindo do OCR."""
    placa = corrigir_placa(texto_bruto)
    formato = formato_placa(placa) if placa else None
    return Leitura(normalizar(texto_bruto), confiancas, placa, formato)


class LeitorDePlacas:
    """Envolve o OCR da fast-plate-ocr para o resto do projeto não depender da biblioteca."""

    def __init__(self, modelo: str = MODELO_PADRAO):
        # Só CPU, como na detecção.
        self._ocr = LicensePlateRecognizer(modelo, providers=["CPUExecutionProvider"])
        self._modo_cor = self._ocr.config.image_color_mode

    def ler(self, recorte: np.ndarray) -> Leitura:
        """Lê um recorte de placa em BGR (como vem do OpenCV)."""
        # A biblioteca espera a imagem já no modo de cor do modelo, não em BGR.
        if self._modo_cor == "rgb":
            imagem = cv2.cvtColor(recorte, cv2.COLOR_BGR2RGB)
        else:
            imagem = cv2.cvtColor(recorte, cv2.COLOR_BGR2GRAY)

        previsao = self._ocr.run(imagem, return_confidence=True)[0]
        texto = previsao.plate
        # char_probs tem uma posição por "vaga" do modelo; as que sobram depois do texto são preenchimento.
        confiancas = [float(p) for p in previsao.char_probs[: len(texto)]]
        return interpretar(texto, confiancas)


def main() -> int:
    parser = argparse.ArgumentParser(description="Encontra e lê as placas numa foto (ou num quadro de vídeo).")
    parser.add_argument("arquivo", help="foto (.jpg, .png) ou vídeo")
    parser.add_argument("--quadro", type=int, default=0, help="número do quadro, se o arquivo for vídeo (padrão: 0)")
    parser.add_argument("--salvar", help="salva a imagem marcada neste caminho em vez de abrir a janela")
    parser.add_argument("--largura", type=int, default=1280, help="largura máxima da janela (padrão: 1280)")
    args = parser.parse_args()

    imagem = ler_imagem(args.arquivo, args.quadro)
    if imagem is None:
        print(f"Não foi possível abrir: {args.arquivo}", file=sys.stderr)
        return 1

    detector = DetectorDePlacas()
    leitor = LeitorDePlacas()

    deteccoes = detector.detectar(imagem)
    print(f"{len(deteccoes)} placa(s) encontrada(s)")
    for d in deteccoes:
        leitura = leitor.ler(recortar(imagem, d))
        letras = " ".join(f"{c}:{p:.2f}" for c, p in zip(leitura.texto_bruto, leitura.confiancas))
        print(f"  lido={leitura.texto_bruto!r}  placa={leitura.placa}  formato={leitura.formato}")
        print(f"    detecção={d.confianca:.2f}  leitura={leitura.confianca:.2f}  por caractere: {letras}")

        if leitura.placa:
            desenhar_caixa(imagem, d.x1, d.y1, d.x2, d.y2, f"{leitura.placa} {leitura.confianca:.0%}")
        else:
            # Placa encontrada, mas o texto não é uma placa brasileira válida.
            cv2.rectangle(imagem, (d.x1, d.y1), (d.x2, d.y2), VERMELHO, 2)

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
