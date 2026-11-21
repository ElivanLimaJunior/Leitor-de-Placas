"""Inicia o painel web: python -m leitor.web [--video ARQUIVO | --camera-env | --demo ARQUIVO]"""

import argparse
import logging
import os
import sys

import uvicorn

from leitor import config as cfg
from leitor import demo as dm
from leitor.banco import CAMINHO_PADRAO
from leitor.camera import abrir_instavel, carregar_env
from leitor.motor import ENTRADA, SAIDA
from leitor.web.app import criar_app


def main() -> int:
    parser = argparse.ArgumentParser(description="Painel web da portaria do estacionamento.")
    fonte = parser.add_mutually_exclusive_group()
    fonte.add_argument("--video", help="arquivo de vídeo, endereço rtsp:// ou número da webcam")
    fonte.add_argument("--camera-env", action="store_true", help="usa o endereço CAMERA_URL do arquivo .env")
    fonte.add_argument(
        "--demo",
        metavar="VIDEO",
        help=f"demonstração: o vídeo serve de câmera da entrada e depois da saída (banco próprio em {dm.CAMINHO_BANCO})",
    )
    parser.add_argument("--demo-segundos", type=float, default=30, help="trecho do vídeo usado em cada fase (padrão: 30)")
    parser.add_argument("--demo-horas", type=float, default=2, help="horas que passam entre entrada e saída (padrão: 2)")
    parser.add_argument("--repetir", action="store_true", help="recomeça o vídeo quando ele termina")
    parser.add_argument("--tipo", choices=[ENTRADA, SAIDA], default=ENTRADA, help="a câmera filma a entrada ou a saída")
    parser.add_argument(
        "--simular-queda",
        type=int,
        metavar="QUADROS",
        help="derruba a conexão a cada N quadros, para ver a reconexão automática",
    )
    parser.add_argument("--banco", default=str(CAMINHO_PADRAO), help=f"arquivo do banco (padrão: {CAMINHO_PADRAO})")
    parser.add_argument("--config", default=str(cfg.CAMINHO_PADRAO), help="arquivo de configuração")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="127.0.0.1 = só este computador; 0.0.0.0 = outros aparelhos da rede (ex.: celular da portaria)",
    )
    parser.add_argument("--porta", type=int, default=8000)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    endereco = args.video
    if args.camera_env:
        carregar_env()
        endereco = os.environ.get("CAMERA_URL")
        if not endereco:
            print("CAMERA_URL não encontrado no arquivo .env (veja .env.example).", file=sys.stderr)
            return 1

    demo = None
    banco = args.banco
    if args.demo:
        if not os.path.isfile(args.demo):
            print(f"Vídeo não encontrado: {args.demo}", file=sys.stderr)
            return 1
        demo = dm.ConfigDemo(args.demo, segundos=args.demo_segundos, horas=args.demo_horas)
        banco = str(dm.CAMINHO_BANCO)
        try:
            dm.preparar_banco(banco, cfg.carregar(args.config), demo.carros_dentro)
        except PermissionError:
            print(f"Não deu para recriar {banco}: a demonstração já está aberta em outra janela? Feche-a e tente de novo.",
                  file=sys.stderr)
            return 1

    app = criar_app(
        banco,
        args.config,
        fonte=endereco,
        repetir=args.repetir,
        tipo_camera=args.tipo,
        abrir_captura=abrir_instavel(args.simular_queda) if args.simular_queda else None,
        demo=demo,
    )
    print(f"Painel em http://{'localhost' if args.host == '127.0.0.1' else args.host}:{args.porta}")
    uvicorn.run(app, host=args.host, port=args.porta, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
