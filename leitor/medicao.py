"""Etapa 5: medir antes de confiar.

Dois passos:
1. coletar: roda detecção + OCR em quadros do vídeo e salva todas as leituras numa planilha,
   além de um rascunho de gabarito com as placas candidatas.
   Para montar o gabarito, o comando conferir mostra o vídeo quadro a quadro com as leituras.
2. avaliar: compara as leituras com o gabarito (as placas certas, conferidas por você)
   para vários limites de confiança.

As planilhas usam ";" como separador para abrir direto no Excel em português.
"""

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cv2

from leitor.deteccao import DetectorDePlacas, MODELO_PADRAO, recortar
from leitor.ocr import VERMELHO, LeitorDePlacas
from leitor.video import TECLA_ESC, desenhar_caixa, escrever_info, redimensionar

SEPARADOR = ";"
# utf-8-sig faz o Excel reconhecer os acentos.
CODIFICACAO = "utf-8-sig"

# Na coleta, o detector aceita até caixas fracas: quem decide o corte é a avaliação, olhando os números.
CONFIANCA_MINIMA_COLETA = 0.10

COLUNAS = ["quadro", "x1", "y1", "x2", "y2", "conf_deteccao", "texto_bruto", "placa", "conf_leitura"]


@dataclass
class LeituraColetada:
    quadro: int
    conf_deteccao: float
    texto_bruto: str
    placa: str | None
    conf_leitura: float
    largura: int = 0
    """Largura da placa na imagem, em pixels: placas pequenas (longe) são lidas pior."""


@dataclass
class Resultado:
    """Números de uma avaliação, para uma combinação de limites."""

    aceitas: int
    """Leituras válidas que passaram dos limites."""
    corretas: int
    """Aceitas cuja placa está no gabarito."""
    erradas: Counter
    """Falsos positivos: placas aceitas que não estão no gabarito (placa -> quantas vezes)."""
    encontradas: set[str]
    """Placas do gabarito lidas certo pelo menos uma vez."""
    perdidas: set[str]
    """Falsos negativos: placas do gabarito que nunca foram lidas certo."""

    @property
    def precisao(self) -> float:
        """De cada 100 leituras aceitas, quantas estão certas."""
        return self.corretas / self.aceitas if self.aceitas else 0.0


def avaliar(
    leituras: list[LeituraColetada],
    gabarito: set[str],
    limite_leitura: float,
    limite_deteccao: float = 0.0,
    largura_minima: int = 0,
) -> Resultado:
    aceitas = [
        l
        for l in leituras
        if l.placa
        and l.conf_leitura >= limite_leitura
        and l.conf_deteccao >= limite_deteccao
        and l.largura >= largura_minima
    ]
    corretas = [l for l in aceitas if l.placa in gabarito]
    erradas = Counter(l.placa for l in aceitas if l.placa not in gabarito)
    encontradas = {l.placa for l in corretas}
    return Resultado(len(aceitas), len(corretas), erradas, encontradas, gabarito - encontradas)


def ler_leituras(caminho: Path) -> list[LeituraColetada]:
    with caminho.open(encoding=CODIFICACAO, newline="") as arquivo:
        return [
            LeituraColetada(
                quadro=int(linha["quadro"]),
                conf_deteccao=float(linha["conf_deteccao"]),
                texto_bruto=linha["texto_bruto"],
                placa=linha["placa"] or None,
                conf_leitura=float(linha["conf_leitura"]),
                largura=int(linha["x2"]) - int(linha["x1"]),
            )
            for linha in csv.DictReader(arquivo, delimiter=SEPARADOR)
        ]


def ler_gabarito(caminho: Path) -> set[str]:
    """Lê a coluna "placa" do gabarito, ignorando linhas vazias."""
    with caminho.open(encoding=CODIFICACAO, newline="") as arquivo:
        return {
            linha["placa"].strip().upper()
            for linha in csv.DictReader(arquivo, delimiter=SEPARADOR)
            if linha["placa"].strip()
        }


def coletar(video: str, passo: int, modelo: str, saida: Path, rascunho: Path) -> int:
    captura = cv2.VideoCapture(video)
    if not captura.isOpened():
        print(f"Não foi possível abrir o vídeo: {video}", file=sys.stderr)
        return 1

    total = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))
    detector = DetectorDePlacas(modelo, confianca_minima=CONFIANCA_MINIMA_COLETA)
    leitor = LeitorDePlacas()

    saida.parent.mkdir(parents=True, exist_ok=True)
    candidatas: dict[str, list[int]] = {}
    numero = -1
    with saida.open("w", encoding=CODIFICACAO, newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=SEPARADOR)
        escritor.writerow(COLUNAS)
        while True:
            ok, quadro = captura.read()
            if not ok:
                break
            numero += 1
            if numero % passo:
                continue
            for d in detector.detectar(quadro):
                leitura = leitor.ler(recortar(quadro, d))
                escritor.writerow(
                    [numero, d.x1, d.y1, d.x2, d.y2, f"{d.confianca:.3f}",
                     leitura.texto_bruto, leitura.placa or "", f"{leitura.confianca:.3f}"]
                )
                if leitura.placa:
                    candidatas.setdefault(leitura.placa, []).append(numero)
            print(f"\rquadro {numero}/{total}", end="", flush=True)
    captura.release()
    print(f"\nLeituras salvas em {saida}")

    if rascunho.exists():
        print(f"Rascunho de gabarito já existe, não sobrescrevi: {rascunho}")
        return 0
    rascunho.parent.mkdir(parents=True, exist_ok=True)
    with rascunho.open("w", encoding=CODIFICACAO, newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=SEPARADOR)
        escritor.writerow(["placa", "vezes", "primeiro_quadro"])
        for placa, quadros in sorted(candidatas.items(), key=lambda item: item[1][0]):
            escritor.writerow([placa, len(quadros), quadros[0]])
    print(f"Rascunho de gabarito com {len(candidatas)} placa(s) candidata(s) em {rascunho}")
    print("Confira cada uma no vídeo antes de usar como gabarito.")
    return 0


def conferir(video: str, inicio: int, largura: int) -> int:
    """Mostra o vídeo com as leituras por cima, para conferir placas e montar o gabarito.

    Teclas: espaço pausa/retoma; com o vídeo pausado, d avança e a volta um quadro; q ou Esc fecha.
    """
    captura = cv2.VideoCapture(video)
    if not captura.isOpened():
        print(f"Não foi possível abrir o vídeo: {video}", file=sys.stderr)
        return 1

    total = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))
    detector = DetectorDePlacas()
    leitor = LeitorDePlacas()
    janela = "Conferir placas"
    numero = max(min(inicio, total - 1), 0)
    pausado = False
    captura.set(cv2.CAP_PROP_POS_FRAMES, numero)

    while True:
        ok, quadro = captura.read()
        if not ok:
            break

        for d in detector.detectar(quadro):
            leitura = leitor.ler(recortar(quadro, d))
            if leitura.placa:
                desenhar_caixa(quadro, d.x1, d.y1, d.x2, d.y2, f"{leitura.placa} {leitura.confianca:.0%}")
            else:
                cv2.rectangle(quadro, (d.x1, d.y1), (d.x2, d.y2), VERMELHO, 2)

        quadro = redimensionar(quadro, largura)
        estado = "PAUSADO | a/d: quadro anterior/seguinte" if pausado else "espaco: pausa"
        escrever_info(quadro, f"quadro {numero}/{total} | {estado} | q/Esc: sair")
        cv2.imshow(janela, quadro)

        # Pausado, espera uma tecla; rodando, só dá tempo de a janela atualizar.
        tecla = cv2.waitKey(0 if pausado else 1) & 0xFF
        if tecla in (ord("q"), TECLA_ESC) or cv2.getWindowProperty(janela, cv2.WND_PROP_VISIBLE) < 1:
            break
        if tecla == ord(" "):
            pausado = not pausado
        if not pausado or tecla == ord("d"):
            numero += 1  # o próximo read() já entrega o quadro seguinte
            continue
        if tecla == ord("a"):
            numero = max(numero - 1, 0)
        # Voltar ou mostrar de novo o mesmo quadro exige buscar a posição (mais lento num MP4).
        captura.set(cv2.CAP_PROP_POS_FRAMES, numero)

    captura.release()
    cv2.destroyAllWindows()
    return 0


def _linha(rotulo: str, r: Resultado, total_gabarito: int) -> str:
    return (
        f"  {rotulo:>6}  {r.aceitas:7d}  {r.corretas:8d}  {sum(r.erradas.values()):11d}"
        f"  {r.precisao:8.1%}  {len(r.encontradas):5d} de {total_gabarito:<4d}  {len(r.perdidas):12d}"
    )


CABECALHO = "  aceitas  corretas  erradas(FP)  precisão  placas lidas  perdidas(FN)"


def imprimir_avaliacao(
    leituras: list[LeituraColetada], gabarito: set[str], limite: float, limite_deteccao: float, largura_minima: int
) -> None:
    validas = sum(1 for l in leituras if l.placa)
    print(f"{len(leituras)} leituras, {validas} formaram placa válida. Gabarito: {len(gabarito)} placas.")
    print(f"Limite de detecção fixo em {limite_deteccao:.2f}.")

    print(f"\nPor confiança mínima da leitura (largura mínima fixa em {largura_minima} px):")
    print("limite" + CABECALHO)
    for i in range(0, 20):
        r = avaliar(leituras, gabarito, i / 20, limite_deteccao, largura_minima)
        print(_linha(f"{i / 20:.2f}", r, len(gabarito)))

    print(f"\nPor largura mínima da placa (confiança mínima fixa em {limite:.2f}):")
    print("    px" + CABECALHO)
    for largura in range(0, 130, 10):
        r = avaliar(leituras, gabarito, limite, limite_deteccao, largura)
        print(_linha(str(largura), r, len(gabarito)))


def imprimir_detalhes(
    leituras: list[LeituraColetada], gabarito: set[str], limite: float, limite_deteccao: float, largura_minima: int
) -> None:
    r = avaliar(leituras, gabarito, limite, limite_deteccao, largura_minima)
    print(f"\nDetalhes com confiança mínima {limite:.2f} e largura mínima {largura_minima} px:")
    print(f"  Acerta {len(r.encontradas)} de {len(gabarito)} placas; {r.corretas} de {r.aceitas} leituras aceitas estão certas.")
    if r.erradas:
        print("  Falsos positivos (lidas, mas fora do gabarito):")
        for placa, vezes in r.erradas.most_common():
            print(f"    {placa}  ({vezes}x)")
    if r.perdidas:
        print("  Falsos negativos (no gabarito, nunca lidas certo):")
        for placa in sorted(r.perdidas):
            print(f"    {placa}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mede a taxa de acerto da leitura de placas.")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_coletar = sub.add_parser("coletar", help="roda detecção + OCR no vídeo e salva as leituras")
    p_coletar.add_argument("video")
    p_coletar.add_argument("--passo", type=int, default=10, help="analisa 1 a cada N quadros (padrão: 10)")
    p_coletar.add_argument("--modelo", default=MODELO_PADRAO, help=f"modelo de detecção (padrão: {MODELO_PADRAO})")
    p_coletar.add_argument("--saida", help="planilha de leituras (padrão: capturas/leituras_<video>.csv)")

    p_conferir = sub.add_parser("conferir", help="mostra o vídeo com as leituras, para montar o gabarito")
    p_conferir.add_argument("video")
    p_conferir.add_argument("--inicio", type=int, default=0, help="quadro onde começar (padrão: 0)")
    p_conferir.add_argument("--largura", type=int, default=1280, help="largura máxima da janela (padrão: 1280)")

    p_avaliar = sub.add_parser("avaliar", help="compara as leituras com o gabarito")
    p_avaliar.add_argument("leituras", help="planilha gerada pelo coletar")
    p_avaliar.add_argument("gabarito", help="planilha com a coluna 'placa' conferida por você")
    p_avaliar.add_argument("--deteccao", type=float, default=0.0, help="limite mínimo de confiança da detecção")
    p_avaliar.add_argument("--limite", type=float, default=0.0, help="confiança mínima da leitura (padrão: 0)")
    p_avaliar.add_argument("--largura-minima", type=int, default=0, help="largura mínima da placa em pixels (padrão: 0)")

    args = parser.parse_args()

    if args.comando == "coletar":
        nome = Path(args.video).stem
        saida = Path(args.saida) if args.saida else Path("capturas") / f"leituras_{nome}.csv"
        rascunho = Path("data") / f"gabarito_{nome}.csv"
        return coletar(args.video, args.passo, args.modelo, saida, rascunho)
    if args.comando == "conferir":
        return conferir(args.video, args.inicio, args.largura)

    leituras = ler_leituras(Path(args.leituras))
    gabarito = ler_gabarito(Path(args.gabarito))
    imprimir_avaliacao(leituras, gabarito, args.limite, args.deteccao, args.largura_minima)
    imprimir_detalhes(leituras, gabarito, args.limite, args.deteccao, args.largura_minima)
    return 0


if __name__ == "__main__":
    sys.exit(main())
