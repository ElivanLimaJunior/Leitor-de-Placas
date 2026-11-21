"""Etapa 10: câmera de verdade.

- Lê a câmera (RTSP, webcam ou arquivo de vídeo) numa thread separada, para não travar quem processa.
- Guarda só o quadro mais recente: se o processamento for mais lento que a câmera, os quadros
  antigos são descartados, em vez de acumular atraso.
- Se a conexão cair, tenta reconectar sozinha, esperando um pouco mais a cada tentativa.

O endereço da câmera (que pode ter usuário e senha) fica no arquivo .env, fora do Git.
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

LOG = logging.getLogger(__name__)

ESPERA_INICIAL_S = 1.0
ESPERA_MAXIMA_S = 30.0


def carregar_env(caminho: Path | str = ".env") -> None:
    """Lê linhas CHAVE=valor do arquivo .env para as variáveis de ambiente (sem sobrescrever as que já existem)."""
    caminho = Path(caminho)
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def esconder_senha(fonte: str) -> str:
    """rtsp://usuario:senha@ip/... -> rtsp://usuario:***@ip/..., para poder aparecer em log e na tela."""
    if "://" in fonte and "@" in fonte:
        protocolo, resto = fonte.split("://", 1)
        credenciais, endereco = resto.rsplit("@", 1)
        if ":" in credenciais:
            usuario = credenciais.split(":", 1)[0]
            return f"{protocolo}://{usuario}:***@{endereco}"
    return fonte


def _eh_arquivo(fonte: str) -> bool:
    return Path(fonte).is_file()


class Camera:
    def __init__(
        self,
        fonte: str,
        repetir: bool = False,
        abrir: Callable[[str], cv2.VideoCapture] = cv2.VideoCapture,
    ):
        """
        fonte: endereço rtsp://..., número da webcam ("0") ou caminho de um arquivo de vídeo.
        repetir: para arquivo de vídeo, volta ao começo quando termina (útil para demonstração).
        abrir: função que abre a captura. Trocada nos testes para simular quedas.
        """
        self.fonte = fonte
        self.repetir = repetir
        self._abrir = abrir
        self._arquivo = _eh_arquivo(fonte)
        self._quadro: np.ndarray | None = None
        self._numero = -1
        self._lido = -1
        self._trava = threading.Lock()
        self._novo = threading.Condition(self._trava)
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self.conectada = False
        self.terminou = False
        """Só para arquivo sem repetir: o vídeo chegou ao fim."""
        self.fps = 30.0
        self.reconexoes = 0

    def iniciar(self) -> "Camera":
        self._thread = threading.Thread(target=self._rodar, name="camera", daemon=True)
        self._thread.start()
        return self

    def parar(self) -> None:
        self._parar.set()
        with self._novo:
            self._novo.notify_all()
        if self._thread:
            self._thread.join(timeout=5)

    def ler(self, espera_s: float = 1.0) -> tuple[int, np.ndarray] | None:
        """O quadro mais recente que ainda não foi entregue, ou None se nenhum chegou dentro da espera."""
        with self._novo:
            self._novo.wait_for(lambda: self._numero > self._lido or self._parar.is_set() or self.terminou, espera_s)
            if self._numero <= self._lido:
                return None
            self._lido = self._numero
            return self._numero, self._quadro.copy()

    def _abrir_captura(self) -> cv2.VideoCapture | None:
        fonte = int(self.fonte) if self.fonte.isdigit() else self.fonte
        captura = self._abrir(fonte)
        if not captura.isOpened():
            captura.release()
            return None
        fps = captura.get(cv2.CAP_PROP_FPS)
        if fps and fps > 0:
            self.fps = fps
        return captura

    def _rodar(self) -> None:
        espera = ESPERA_INICIAL_S
        while not self._parar.is_set():
            captura = self._abrir_captura()
            if captura is None:
                LOG.warning("Não conectou em %s. Nova tentativa em %.0f s.", esconder_senha(self.fonte), espera)
                self._parar.wait(espera)
                espera = min(espera * 2, ESPERA_MAXIMA_S)
                continue

            LOG.info("Câmera conectada: %s", esconder_senha(self.fonte))
            self.conectada = True
            espera = ESPERA_INICIAL_S
            fim_normal = self._ler_ate_falhar(captura)
            captura.release()
            self.conectada = False

            if self._parar.is_set():
                break
            if fim_normal:
                if not self.repetir:
                    self.terminou = True
                    with self._novo:
                        self._novo.notify_all()
                    break
                continue  # arquivo terminou: recomeça do início
            self.reconexoes += 1
            LOG.warning("Conexão com a câmera caiu. Reconectando…")

    def _ler_ate_falhar(self, captura: cv2.VideoCapture) -> bool:
        """Lê quadros até a fonte parar. Devolve True se foi o fim normal de um arquivo de vídeo."""
        intervalo = 1 / self.fps
        proximo = time.monotonic()
        while not self._parar.is_set():
            ok, quadro = captura.read()
            if not ok:
                return self._arquivo and self._fim_do_arquivo(captura)
            with self._novo:
                self._quadro = quadro
                self._numero += 1
                self._novo.notify_all()
            if self._arquivo:
                # Arquivo é lido na velocidade real do vídeo, como se fosse uma câmera ao vivo.
                proximo += intervalo
                self._parar.wait(max(proximo - time.monotonic(), 0))
        return False

    @staticmethod
    def _fim_do_arquivo(captura: cv2.VideoCapture) -> bool:
        posicao = captura.get(cv2.CAP_PROP_POS_FRAMES)
        total = captura.get(cv2.CAP_PROP_FRAME_COUNT)
        return total > 0 and posicao >= total - 1


class VideoQuadroAQuadro:
    """Lê um arquivo de vídeo em sequência, entregando 1 a cada `passo` quadros, sem descartar nenhum por atraso.

    Diferente da Camera, o resultado não depende de a máquina estar ocupada: é sempre o mesmo.
    Por isso é usado na demonstração. Se o processamento for mais rápido que o vídeo, espera para
    acompanhar o tempo real; se for mais lento, o vídeo apenas anda mais devagar.
    Tem a mesma interface da Camera (iniciar, ler, parar, conectada, terminou, fps).
    """

    def __init__(self, fonte: str, passo: int = 3):
        self.fonte = fonte
        self.passo = passo
        self.fps = 30.0
        self.conectada = False
        self.terminou = False
        self._captura: cv2.VideoCapture | None = None
        self._numero = -1
        self._inicio = 0.0

    def iniciar(self) -> "VideoQuadroAQuadro":
        self._captura = cv2.VideoCapture(self.fonte)
        self.conectada = self._captura.isOpened()
        self.terminou = not self.conectada
        self.fps = self._captura.get(cv2.CAP_PROP_FPS) or 30.0
        self._inicio = time.monotonic()
        return self

    def ler(self, espera_s: float = 1.0) -> tuple[int, np.ndarray] | None:
        if self.terminou:
            return None
        for _ in range(self.passo - 1):
            self._captura.grab()  # pula sem decodificar: mais rápido
            self._numero += 1
        ok, quadro = self._captura.read()
        if not ok:
            self.terminou = True
            self.conectada = False
            return None
        self._numero += 1
        adiantado = self._inicio + self._numero / self.fps - time.monotonic()
        if adiantado > 0:
            time.sleep(adiantado)
        return self._numero, quadro

    def parar(self) -> None:
        if self._captura is not None:
            self._captura.release()
        self.conectada = False


class CapturaInstavel:
    """Captura que "desliga o cabo" de tempos em tempos. Serve para demonstrar e testar a reconexão.

    Depois de `quadros_ate_cair` leituras, falha como uma câmera de rede que caiu.
    """

    def __init__(self, fonte, quadros_ate_cair: int, abrir=cv2.VideoCapture):
        self._captura = abrir(fonte)
        self._quadros_ate_cair = quadros_ate_cair
        self._lidos = 0
        self._caiu = False

    def isOpened(self) -> bool:
        return self._captura.isOpened()

    def read(self):
        if self._lidos >= self._quadros_ate_cair:
            self._caiu = True
            return False, None
        self._lidos += 1
        return self._captura.read()

    def get(self, propriedade):
        if propriedade == cv2.CAP_PROP_FRAME_COUNT and self._caiu:
            return 0  # câmera de rede não tem "fim do vídeo"
        return self._captura.get(propriedade)

    def set(self, propriedade, valor):
        return self._captura.set(propriedade, valor)

    def release(self) -> None:
        self._captura.release()


def abrir_instavel(quadros_ate_cair: int, tentativas_falhas: int = 2, abrir_real=cv2.VideoCapture) -> Callable:
    """Fábrica de capturas que caem a cada `quadros_ate_cair` quadros e retomam de onde pararam.

    Depois de cada queda, as próximas `tentativas_falhas` tentativas de conexão falham,
    como uma câmera que ficou um tempo fora da rede.
    """
    estado = {"falhas_restantes": 0, "posicao": 0}

    def abrir(fonte):
        if estado["falhas_restantes"] > 0:
            estado["falhas_restantes"] -= 1
            return _CapturaFechada()
        captura = CapturaInstavel(fonte, quadros_ate_cair, abrir_real)
        total = captura.get(cv2.CAP_PROP_FRAME_COUNT)
        if total > 0 and estado["posicao"] >= total:
            estado["posicao"] = 0  # o vídeo acabou: recomeça
        captura.set(cv2.CAP_PROP_POS_FRAMES, estado["posicao"])
        estado["posicao"] += quadros_ate_cair
        estado["falhas_restantes"] = tentativas_falhas
        return captura

    return abrir


class _CapturaFechada:
    """Captura que não conectou."""

    def isOpened(self) -> bool:
        return False

    def release(self) -> None:
        pass
