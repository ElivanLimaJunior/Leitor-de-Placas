"""Etapa 1: abrir um vídeo, mostrar quadro a quadro e desenhar por cima."""

import argparse
import sys

import cv2
import numpy as np

# O OpenCV guarda cores em BGR (azul, verde, vermelho), não em RGB.
VERDE = (0, 255, 0)
BRANCO = (255, 255, 255)
PRETO = (0, 0, 0)

TECLA_ESC = 27


def redimensionar(quadro: np.ndarray, largura_max: int) -> np.ndarray:
    """Reduz o quadro para no máximo `largura_max` pixels de largura, mantendo a proporção."""
    altura, largura = quadro.shape[:2]
    if largura <= largura_max:
        return quadro
    escala = largura_max / largura
    return cv2.resize(quadro, (largura_max, int(altura * escala)), interpolation=cv2.INTER_AREA)


def desenhar_caixa(quadro: np.ndarray, x1: int, y1: int, x2: int, y2: int, texto: str) -> None:
    """Desenha um retângulo com um rótulo em cima, direto no quadro."""
    cv2.rectangle(quadro, (x1, y1), (x2, y2), VERDE, 2)
    (larg_txt, alt_txt), base = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    topo = max(y1 - alt_txt - base - 4, 0)
    # Se o rótulo passar da borda direita, puxa para a esquerda para continuar legível.
    esquerda = max(min(x1, quadro.shape[1] - larg_txt - 8), 0)
    cv2.rectangle(quadro, (esquerda, topo), (esquerda + larg_txt + 8, topo + alt_txt + base + 4), VERDE, -1)
    cv2.putText(quadro, texto, (esquerda + 4, topo + alt_txt + 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, PRETO, 2)


def escrever_info(quadro: np.ndarray, texto: str) -> None:
    """Escreve uma linha de informação no canto superior esquerdo, sobre uma faixa escura para ler em qualquer fundo."""
    (larg_txt, alt_txt), base = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
    cv2.rectangle(quadro, (0, 0), (larg_txt + 20, alt_txt + base + 16), PRETO, -1)
    cv2.putText(quadro, texto, (10, alt_txt + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, BRANCO, 1, cv2.LINE_AA)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mostra um vídeo quadro a quadro com um retângulo desenhado.")
    parser.add_argument("video", help="caminho do arquivo de vídeo")
    parser.add_argument("--largura", type=int, default=1280, help="largura máxima da janela (padrão: 1280)")
    args = parser.parse_args()

    captura = cv2.VideoCapture(args.video)
    if not captura.isOpened():
        print(f"Não foi possível abrir o vídeo: {args.video}", file=sys.stderr)
        return 1

    fps = captura.get(cv2.CAP_PROP_FPS) or 30
    total = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))
    espera_ms = max(int(1000 / fps), 1)
    pausado = False
    numero = 0

    while True:
        if not pausado:
            ok, quadro = captura.read()
            if not ok:
                break  # fim do vídeo
            numero += 1
            quadro = redimensionar(quadro, args.largura)

            altura, largura = quadro.shape[:2]
            # Retângulo fixo no centro, só para provar que dá para desenhar sobre o vídeo.
            desenhar_caixa(quadro, largura // 3, altura // 3, 2 * largura // 3, 2 * altura // 3, "exemplo")
            escrever_info(quadro, f"quadro {numero}/{total} | espaco: pausa | q/Esc: sair")
            cv2.imshow("Leitor de Placas", quadro)

        tecla = cv2.waitKey(espera_ms) & 0xFF
        if tecla in (ord("q"), TECLA_ESC):
            break
        if tecla == ord(" "):
            pausado = not pausado
        if cv2.getWindowProperty("Leitor de Placas", cv2.WND_PROP_VISIBLE) < 1:
            break  # janela fechada no X

    captura.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
