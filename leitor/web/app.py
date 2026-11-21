"""Servidor do painel: API JSON para a página, vídeo ao vivo (MJPEG) e a thread que lê a câmera.

Cada requisição abre a sua própria conexão com o SQLite: as requisições rodam em threads
diferentes, e uma conexão do sqlite3 não pode ser compartilhada entre threads.
"""

import logging
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Literal

import cv2
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from leitor import config as cfg
from leitor.banco import Banco, agora
from leitor.camera import Camera, VideoQuadroAQuadro, esconder_senha
from leitor.demo import ConfigDemo
from leitor.estacionamento import Estacionamento
from leitor.motor import ENTRADA, SAIDA, Evento, Motor
from leitor.placa import normalizar
from leitor.regras import calcular_valor, formatar_reais
from leitor.relogio import RELOGIO
from leitor.video import redimensionar

LOG = logging.getLogger(__name__)
ESTATICOS = Path(__file__).parent / "static"
LARGURA_VIDEO = 960
# Na demonstração, quanto tempo real dura a animação de "passar o tempo".
DURACAO_PASSAGEM_S = 6


@dataclass
class Estado:
    """O que é compartilhado entre a thread da câmera e as requisições."""

    caminho_banco: str
    config: cfg.Config
    eventos: deque = field(default_factory=lambda: deque(maxlen=50))
    camera: Camera | None = None
    jpeg: bytes | None = None
    demo: dict | None = None
    """Na demonstração: a fase atual e a mensagem que o painel mostra."""
    parar: threading.Event = field(default_factory=threading.Event)


class Placa(BaseModel):
    placa: str


class Cadastro(BaseModel):
    placa: str
    proprietario: str
    tipo: Literal["mensalista", "bloqueado"]
    observacao: str = ""


def _rodar_camera(
    estado: Estado,
    estacionamento: Estacionamento,
    camera: Camera | VideoQuadroAQuadro,
    tipo_camera: str,
    limite_s: float | None = None,
) -> None:
    """Pega sempre o quadro mais recente da câmera, processa e guarda o JPEG para o painel.

    Para quando a câmera termina (arquivo sem repetir), quando o app é desligado ou, se houver
    limite_s, quando esse tempo de vídeo passou.
    """
    estado.camera = camera
    camera.iniciar()
    motor = None
    try:
        while not estado.parar.is_set():
            lido = camera.ler(espera_s=1.0)
            if lido is None:
                if camera.terminou:
                    break
                continue
            if motor is None:
                # Só depois de conectar a câmera sabemos o fps dela.
                motor = Motor(camera.fps, estacionamento, tipo_camera, eventos=estado.eventos)
            numero, quadro = lido
            if limite_s is not None and numero >= limite_s * camera.fps:
                break
            motor.processar(numero, quadro)
            ok, jpeg = cv2.imencode(".jpg", redimensionar(quadro, LARGURA_VIDEO), [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                estado.jpeg = jpeg.tobytes()
    finally:
        camera.parar()
        if motor:
            motor.finalizar()


def _processar(estado: Estado, camera: Camera, tipo_camera: str) -> None:
    """Thread de fundo do modo normal: uma câmera, ligada até o app ser desligado."""
    banco = Banco(estado.caminho_banco)
    try:
        _rodar_camera(estado, Estacionamento(banco, estado.config), camera, tipo_camera)
    except Exception:
        LOG.exception("Erro no processamento da câmera")
    finally:
        banco.fechar()


def _demonstrar(estado: Estado, demo: ConfigDemo) -> None:
    """Thread de fundo da demonstração: o mesmo vídeo como câmera da entrada e depois da saída."""
    banco = Banco(estado.caminho_banco)
    estacionamento = Estacionamento(banco, estado.config)

    def fase(nome: str, mensagem: str) -> None:
        estado.demo = {"fase": nome, "mensagem": mensagem}
        LOG.info("Demonstração: %s", mensagem)

    try:
        fase("entrada", "Câmera da ENTRADA: carros chegando ao estacionamento")
        _rodar_camera(estado, estacionamento, VideoQuadroAQuadro(demo.video), ENTRADA, demo.segundos)
        if estado.parar.is_set():
            return

        horas = f"{demo.horas:g} hora{'s' if demo.horas != 1 else ''}"
        fase("tempo", f"⏩ Passando o tempo: {horas} depois…")
        RELOGIO.ajustar(velocidade=demo.horas * 3600 / DURACAO_PASSAGEM_S)
        estado.parar.wait(DURACAO_PASSAGEM_S)

        # Relógio acelerado na saída: quem sai mais tarde no vídeo ficou mais tempo e paga mais.
        RELOGIO.ajustar(velocidade=demo.aceleracao)
        fase("saida", f"Câmera da SAÍDA: os mesmos carros indo embora (1 s = {demo.aceleracao / 60:g} min)")
        _rodar_camera(estado, estacionamento, VideoQuadroAQuadro(demo.video), SAIDA, demo.segundos)

        RELOGIO.ajustar(velocidade=1)
        fase("fim", "Demonstração concluída. Veja o faturamento e o relatório.")
    except Exception:
        LOG.exception("Erro na demonstração")
    finally:
        RELOGIO.ajustar(velocidade=1)
        banco.fechar()


def criar_app(
    caminho_banco: str,
    caminho_config: str = str(cfg.CAMINHO_PADRAO),
    fonte: str | None = None,
    repetir: bool = False,
    tipo_camera: str = ENTRADA,
    abrir_captura: Callable | None = None,
    demo: ConfigDemo | None = None,
) -> FastAPI:
    """Cria o app. Com `fonte`, liga uma câmera; com `demo`, roda a demonstração (o banco já deve estar preparado)."""
    estado = Estado(caminho_banco, cfg.carregar(caminho_config))
    if demo:
        estado.demo = {"fase": "preparando", "mensagem": "Preparando a demonstração…"}

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        thread = None
        if demo:
            thread = threading.Thread(target=_demonstrar, args=(estado, demo), daemon=True)
        elif fonte:
            opcoes = {"abrir": abrir_captura} if abrir_captura else {}
            camera = Camera(fonte, repetir=repetir, **opcoes)
            estado.camera = camera
            thread = threading.Thread(target=_processar, args=(estado, camera, tipo_camera), daemon=True)
        if thread:
            thread.start()
        yield
        estado.parar.set()
        if estado.camera:
            estado.camera.parar()
        if thread:
            thread.join(timeout=10)

    app = FastAPI(title="Portaria do Estacionamento", lifespan=ciclo_de_vida)
    app.state.estado = estado
    app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")

    def abrir_banco() -> Iterator[Banco]:
        banco = Banco(estado.caminho_banco)
        try:
            yield banco
        finally:
            banco.fechar()

    @app.get("/", include_in_schema=False)
    def pagina() -> FileResponse:
        return FileResponse(ESTATICOS / "index.html")

    @app.get("/api/estado")
    def ver_estado(banco: Banco = Depends(abrir_banco)) -> dict:
        referencia = agora()
        dentro = banco.dentro_agora(referencia)
        hoje = referencia[:10]
        camera = estado.camera

        def carro(a) -> dict:
            return {
                "placa": a.placa,
                "tipo": a.tipo,
                "proprietario": a.proprietario,
                "entrada": a.entrada,
                "minutos": a.minutos,
                "vaga": a.vaga,
                # Quanto pagaria se saísse agora.
                "valor_parcial": formatar_reais(calcular_valor(a.minutos, a.tipo, estado.config.precos)),
            }

        por_vaga = {a.vaga: carro(a) for a in dentro if a.vaga}
        return {
            "agora": referencia,
            "vagas": estado.config.vagas,
            "ocupadas": len(dentro),
            "livres": max(estado.config.vagas - len(dentro), 0),
            "faturamento_hoje": formatar_reais(banco.faturamento(hoje, hoje)),
            "demo": estado.demo,
            "camera": {
                "ativa": camera is not None or estado.demo is not None,
                "conectada": bool(camera and camera.conectada),
                "fonte": esconder_senha(camera.fonte) if camera else None,
            },
            "eventos": [e.como_dict() for e in list(estado.eventos)],
            "dentro": [carro(a) for a in reversed(dentro)],  # quem entrou por último aparece primeiro
            "patio": [por_vaga.get(v, {"vaga": v, "placa": None}) for v in range(1, estado.config.vagas + 1)],
        }

    @app.post("/api/entrada")
    def entrada_manual(corpo: Placa, banco: Banco = Depends(abrir_banco)) -> dict:
        # Pelo painel quem decide é o operador: a entrada é gravada mesmo com alerta.
        try:
            decisao = Estacionamento(banco, estado.config).entrada(corpo.placa, forcar=True)
        except ValueError as erro:
            raise HTTPException(400, str(erro))
        if decisao is None:
            raise HTTPException(409, f"{normalizar(corpo.placa)} já está dentro.")
        placa = normalizar(corpo.placa)
        estado.eventos.appendleft(Evento(agora(), placa, decisao.situacao, banco.tipo(placa), decisao.mensagem))
        return {"situacao": decisao.situacao, "mensagem": decisao.mensagem, "vaga": decisao.vaga}

    @app.post("/api/saida")
    def saida_manual(corpo: Placa, banco: Banco = Depends(abrir_banco)) -> dict:
        try:
            saida = Estacionamento(banco, estado.config).saida(corpo.placa)
        except ValueError as erro:
            raise HTTPException(400, str(erro))
        if saida is None:
            raise HTTPException(404, f"{normalizar(corpo.placa)} não tem entrada em aberto.")
        estado.eventos.appendleft(Evento(agora(), saida.placa, SAIDA, banco.tipo(saida.placa), saida.mensagem))
        return {"mensagem": saida.mensagem, "valor": saida.valor, "minutos": saida.minutos}

    @app.get("/api/relatorio")
    def relatorio(de: str, ate: str, banco: Banco = Depends(abrir_banco)) -> dict:
        return {
            "faturamento": formatar_reais(banco.faturamento(de, ate)),
            "por_hora": banco.entradas_por_hora(de, ate),
            "frequentes": [
                {"placa": placa, "tipo": tipo, "total": total} for placa, tipo, total in banco.frequentes(de, ate)
            ],
        }

    @app.get("/api/veiculos")
    def listar_veiculos(banco: Banco = Depends(abrir_banco)) -> list[dict]:
        return banco.listar_veiculos()

    @app.post("/api/veiculos")
    def cadastrar(corpo: Cadastro, banco: Banco = Depends(abrir_banco)) -> dict:
        if not corpo.proprietario.strip():
            raise HTTPException(400, "Informe o proprietário.")
        try:
            banco.cadastrar(corpo.placa, corpo.proprietario.strip(), corpo.tipo, corpo.observacao)
        except ValueError as erro:
            raise HTTPException(400, str(erro))
        return {"mensagem": f"{normalizar(corpo.placa)} cadastrado como {corpo.tipo}."}

    @app.delete("/api/veiculos/{placa}")
    def descadastrar(placa: str, banco: Banco = Depends(abrir_banco)) -> dict:
        try:
            removido = banco.descadastrar(placa)
        except ValueError as erro:
            raise HTTPException(400, str(erro))
        if not removido:
            raise HTTPException(404, "Placa não estava cadastrada.")
        return {"mensagem": "Cadastro removido."}

    @app.get("/quadro.jpg", include_in_schema=False)
    def quadro() -> Response:
        """Só o quadro mais recente, como foto. Útil para salvar o momento ou em telas que não aceitam MJPEG."""
        if estado.jpeg is None:
            raise HTTPException(404, "Nenhum quadro ainda.")
        return Response(estado.jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/video", include_in_schema=False)
    def video() -> StreamingResponse:
        if estado.camera is None and estado.demo is None:
            raise HTTPException(404, "Nenhuma câmera ligada.")
        return StreamingResponse(_mjpeg(estado), media_type="multipart/x-mixed-replace; boundary=quadro")

    return app


def _mjpeg(estado: Estado) -> Iterator[bytes]:
    """Vídeo para o navegador: uma sequência de JPEGs que a tag <img> mostra como vídeo.

    O separador vai logo depois de cada quadro: o navegador só mostra um quadro quando vê o
    separador seguinte, e assim o último quadro aparece mesmo quando o vídeo para.
    """
    enviado = None
    yield b"--quadro\r\n"
    while not estado.parar.is_set():
        jpeg = estado.jpeg
        if jpeg is not None and jpeg is not enviado:
            enviado = jpeg
            cabecalho = f"Content-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n".encode()
            yield cabecalho + jpeg + b"\r\n--quadro\r\n"
        time.sleep(0.04)
