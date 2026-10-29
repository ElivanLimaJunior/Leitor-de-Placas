"""Etapa 7: banco de dados do estacionamento (SQLite).

Tabelas:
- veiculos: placas cadastradas (mensalistas e bloqueados). Carros avulsos não precisam de cadastro.
- acessos: uma linha por passagem, com entrada e saída. Saída vazia = o carro ainda está dentro.

Datas ficam como texto "AAAA-MM-DD HH:MM:SS", que o SQLite sabe comparar e usar em contas.
"""

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from leitor.placa import normalizar, placa_valida

CAMINHO_PADRAO = Path("data") / "estacionamento.db"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"

MENSALISTA = "mensalista"
BLOQUEADO = "bloqueado"
AVULSO = "avulso"
"""Tipo de quem não está cadastrado. Não é gravado na tabela veiculos."""

ESQUEMA = """
CREATE TABLE IF NOT EXISTS veiculos (
    placa         TEXT PRIMARY KEY,
    proprietario  TEXT NOT NULL,
    tipo          TEXT NOT NULL CHECK (tipo IN ('mensalista', 'bloqueado')),
    observacao    TEXT,
    cadastrado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS acessos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    placa      TEXT NOT NULL,
    entrada    TEXT NOT NULL,
    saida      TEXT,
    confianca  REAL,
    CHECK (saida IS NULL OR saida >= entrada)
);

-- Consultas por placa e por data ficam rápidas com estes índices.
CREATE INDEX IF NOT EXISTS idx_acessos_placa ON acessos (placa);
CREATE INDEX IF NOT EXISTS idx_acessos_entrada ON acessos (entrada);
-- No máximo um acesso em aberto por placa: o mesmo carro não pode estar dentro duas vezes.
CREATE UNIQUE INDEX IF NOT EXISTS idx_acessos_aberto ON acessos (placa) WHERE saida IS NULL;
"""


@dataclass
class Acesso:
    id: int
    placa: str
    entrada: str
    saida: str | None
    tipo: str
    """mensalista, bloqueado ou avulso."""
    proprietario: str | None
    minutos: float
    """Tempo de permanência. Se o carro ainda está dentro, é o tempo até agora."""


def agora() -> str:
    return datetime.now().strftime(FORMATO_DATA)


def _placa(texto: str) -> str:
    placa = normalizar(texto)
    if not placa_valida(placa):
        raise ValueError(f"Placa inválida: {texto}")
    return placa


class Banco:
    def __init__(self, caminho: Path | str = CAMINHO_PADRAO):
        if str(caminho) != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.conexao = sqlite3.connect(caminho)
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript(ESQUEMA)

    def fechar(self) -> None:
        self.conexao.close()

    # --- cadastro ---

    def cadastrar(self, placa: str, proprietario: str, tipo: str, observacao: str = "", quando: str | None = None) -> None:
        """Cadastra ou atualiza um veículo."""
        with self.conexao:
            self.conexao.execute(
                """INSERT INTO veiculos (placa, proprietario, tipo, observacao, cadastrado_em)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (placa) DO UPDATE SET
                       proprietario = excluded.proprietario, tipo = excluded.tipo, observacao = excluded.observacao""",
                (_placa(placa), proprietario, tipo, observacao, quando or agora()),
            )

    def descadastrar(self, placa: str) -> bool:
        with self.conexao:
            return self.conexao.execute("DELETE FROM veiculos WHERE placa = ?", (_placa(placa),)).rowcount > 0

    def tipo(self, placa: str) -> str:
        linha = self.conexao.execute("SELECT tipo FROM veiculos WHERE placa = ?", (_placa(placa),)).fetchone()
        return linha["tipo"] if linha else AVULSO

    # --- entradas e saídas ---

    def registrar_entrada(self, placa: str, quando: str | None = None, confianca: float | None = None) -> int | None:
        """Abre um acesso. Devolve o id, ou None se o carro já estava dentro (leitura repetida)."""
        try:
            with self.conexao:
                cursor = self.conexao.execute(
                    "INSERT INTO acessos (placa, entrada, confianca) VALUES (?, ?, ?)",
                    (_placa(placa), quando or agora(), confianca),
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None  # o índice único barrou um segundo acesso em aberto

    def registrar_saida(self, placa: str, quando: str | None = None) -> int | None:
        """Fecha o acesso em aberto da placa. Devolve o id, ou None se não havia entrada."""
        with self.conexao:
            linha = self.conexao.execute(
                "SELECT id FROM acessos WHERE placa = ? AND saida IS NULL", (_placa(placa),)
            ).fetchone()
            if linha is None:
                return None
            self.conexao.execute("UPDATE acessos SET saida = ? WHERE id = ?", (quando or agora(), linha["id"]))
            return linha["id"]

    # --- consultas ---

    def _acessos(self, onde: str, parametros: tuple, referencia: str | None) -> list[Acesso]:
        # Para quem ainda está dentro, a permanência é contada até a "referência" (por padrão, agora).
        linhas = self.conexao.execute(
            f"""SELECT a.id, a.placa, a.entrada, a.saida,
                       COALESCE(v.tipo, '{AVULSO}') AS tipo, v.proprietario,
                       (julianday(COALESCE(a.saida, ?)) - julianday(a.entrada)) * 24 * 60 AS minutos
                FROM acessos a
                LEFT JOIN veiculos v ON v.placa = a.placa
                WHERE {onde}
                ORDER BY a.entrada""",
            (referencia or agora(), *parametros),
        ).fetchall()
        return [Acesso(**dict(linha)) for linha in linhas]

    def dentro_agora(self, referencia: str | None = None) -> list[Acesso]:
        """Quem está dentro agora?"""
        return self._acessos("a.saida IS NULL", (), referencia)

    def historico(self, placa: str, referencia: str | None = None) -> list[Acesso]:
        """Quanto tempo o carro X ficou? Todas as passagens dele, com a permanência de cada uma."""
        return self._acessos("a.placa = ?", (_placa(placa),), referencia)

    def acessos_do_dia(self, dia: str, referencia: str | None = None) -> list[Acesso]:
        """Acessos com entrada no dia (AAAA-MM-DD)."""
        return self._acessos("date(a.entrada) = ?", (dia,), referencia)


def _imprimir(acessos: list[Acesso]) -> None:
    if not acessos:
        print("  (nenhum)")
    for a in acessos:
        saida = a.saida or "ainda dentro"
        dono = f" ({a.proprietario})" if a.proprietario else ""
        horas, minutos = divmod(round(a.minutos), 60)
        print(f"  {a.placa}  {a.tipo}{dono}  entrada {a.entrada}  saída {saida}  permanência {horas}h{minutos:02d}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Consulta e cadastro do banco do estacionamento.")
    parser.add_argument("--banco", default=str(CAMINHO_PADRAO), help=f"arquivo do banco (padrão: {CAMINHO_PADRAO})")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("cadastrar", help="cadastra mensalista ou bloqueado")
    p.add_argument("placa")
    p.add_argument("proprietario")
    p.add_argument("tipo", choices=[MENSALISTA, BLOQUEADO])
    p.add_argument("--observacao", default="")

    p = sub.add_parser("descadastrar", help="remove um cadastro")
    p.add_argument("placa")

    p = sub.add_parser("entrada", help="registra uma entrada à mão")
    p.add_argument("placa")
    p.add_argument("--quando", help="AAAA-MM-DD HH:MM:SS (padrão: agora)")

    p = sub.add_parser("saida", help="registra uma saída à mão")
    p.add_argument("placa")
    p.add_argument("--quando", help="AAAA-MM-DD HH:MM:SS (padrão: agora)")

    sub.add_parser("dentro", help="quem está dentro agora?")

    p = sub.add_parser("historico", help="todas as passagens de uma placa e quanto tempo ficou")
    p.add_argument("placa")

    p = sub.add_parser("dia", help="acessos de um dia")
    p.add_argument("data", help="AAAA-MM-DD")

    args = parser.parse_args()
    banco = Banco(args.banco)
    try:
        if args.comando == "cadastrar":
            banco.cadastrar(args.placa, args.proprietario, args.tipo, args.observacao)
            print(f"{normalizar(args.placa)} cadastrado como {args.tipo}.")
        elif args.comando == "descadastrar":
            print("Removido." if banco.descadastrar(args.placa) else "Placa não estava cadastrada.")
        elif args.comando == "entrada":
            ok = banco.registrar_entrada(args.placa, args.quando)
            print("Entrada registrada." if ok else "Essa placa já está dentro.")
        elif args.comando == "saida":
            ok = banco.registrar_saida(args.placa, args.quando)
            print("Saída registrada." if ok else "Essa placa não tem entrada em aberto.")
        elif args.comando == "dentro":
            dentro = banco.dentro_agora()
            print(f"{len(dentro)} veículo(s) dentro agora:")
            _imprimir(dentro)
        elif args.comando == "historico":
            historico = banco.historico(args.placa)
            print(f"Passagens de {normalizar(args.placa)}:")
            _imprimir(historico)
        elif args.comando == "dia":
            acessos = banco.acessos_do_dia(args.data)
            print(f"Acessos em {args.data}:")
            _imprimir(acessos)
    except ValueError as erro:
        print(erro, file=sys.stderr)
        return 1
    finally:
        banco.fechar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
