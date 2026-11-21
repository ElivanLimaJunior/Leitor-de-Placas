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
from pathlib import Path

from leitor.placa import normalizar, placa_valida
from leitor.relogio import RELOGIO

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
    valor      INTEGER,  -- valor pago na saída, em centavos
    vaga       INTEGER,  -- número da vaga ocupada enquanto o carro está dentro
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
    valor: int | None
    """Valor pago na saída, em centavos. None enquanto o carro está dentro."""
    vaga: int | None
    """Vaga ocupada. None se entrou sem vaga livre (liberado à mão com o pátio cheio)."""


def agora() -> str:
    """Hora atual do sistema (na demonstração, o relógio pode estar adiantado ou acelerado)."""
    return RELOGIO.agora().strftime(FORMATO_DATA)


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
        self._migrar()

    def _migrar(self) -> None:
        """Atualiza bancos criados por versões anteriores (valor e vaga vieram na etapa 8)."""
        colunas = {linha["name"] for linha in self.conexao.execute("PRAGMA table_info(acessos)")}
        with self.conexao:
            for coluna in ("valor", "vaga"):
                if coluna not in colunas:
                    self.conexao.execute(f"ALTER TABLE acessos ADD COLUMN {coluna} INTEGER")
            # Duas placas dentro não podem ocupar a mesma vaga.
            self.conexao.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_acessos_vaga ON acessos (vaga) "
                "WHERE saida IS NULL AND vaga IS NOT NULL"
            )

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

    def listar_veiculos(self) -> list[dict]:
        linhas = self.conexao.execute(
            "SELECT placa, proprietario, tipo, observacao, cadastrado_em FROM veiculos ORDER BY tipo, placa"
        ).fetchall()
        return [dict(linha) for linha in linhas]

    def tipo(self, placa: str) -> str:
        linha = self.conexao.execute("SELECT tipo FROM veiculos WHERE placa = ?", (_placa(placa),)).fetchone()
        return linha["tipo"] if linha else AVULSO

    # --- entradas e saídas ---

    def registrar_entrada(
        self, placa: str, quando: str | None = None, confianca: float | None = None, vaga: int | None = None
    ) -> int | None:
        """Abre um acesso. Devolve o id, ou None se o carro já estava dentro (leitura repetida)."""
        try:
            with self.conexao:
                cursor = self.conexao.execute(
                    "INSERT INTO acessos (placa, entrada, confianca, vaga) VALUES (?, ?, ?, ?)",
                    (_placa(placa), quando or agora(), confianca, vaga),
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None  # um índice único barrou: carro já dentro ou vaga já ocupada

    def vagas_ocupadas(self) -> set[int]:
        linhas = self.conexao.execute("SELECT vaga FROM acessos WHERE saida IS NULL AND vaga IS NOT NULL")
        return {linha["vaga"] for linha in linhas}

    def registrar_saida(self, placa: str, quando: str | None = None, valor: int | None = None) -> int | None:
        """Fecha o acesso em aberto da placa, com o valor pago (centavos). Devolve o id, ou None se não havia entrada."""
        with self.conexao:
            linha = self.conexao.execute(
                "SELECT id FROM acessos WHERE placa = ? AND saida IS NULL", (_placa(placa),)
            ).fetchone()
            if linha is None:
                return None
            self.conexao.execute(
                "UPDATE acessos SET saida = ?, valor = ? WHERE id = ?", (quando or agora(), valor, linha["id"])
            )
            return linha["id"]

    # --- consultas ---

    def _acessos(self, onde: str, parametros: tuple, referencia: str | None) -> list[Acesso]:
        # Para quem ainda está dentro, a permanência é contada até a "referência" (por padrão, agora).
        linhas = self.conexao.execute(
            f"""SELECT a.id, a.placa, a.entrada, a.saida,
                       COALESCE(v.tipo, '{AVULSO}') AS tipo, v.proprietario,
                       (julianday(COALESCE(a.saida, ?)) - julianday(a.entrada)) * 24 * 60 AS minutos,
                       a.valor, a.vaga
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

    def acesso_aberto(self, placa: str, referencia: str | None = None) -> Acesso | None:
        """O acesso em aberto da placa (o carro está dentro), ou None."""
        acessos = self._acessos("a.placa = ? AND a.saida IS NULL", (_placa(placa),), referencia)
        return acessos[0] if acessos else None

    def apagar_antigos(self, dias: int, referencia: str | None = None) -> int:
        """LGPD: apaga passagens encerradas há mais de `dias` dias. Devolve quantas foram apagadas.

        Carros ainda dentro nunca são apagados. O cadastro de mensalistas e bloqueados fica.
        """
        with self.conexao:
            cursor = self.conexao.execute(
                "DELETE FROM acessos WHERE saida IS NOT NULL AND julianday(?) - julianday(saida) > ?",
                (referencia or agora(), dias),
            )
            return cursor.rowcount

    # --- relatórios ---

    def entradas_por_hora(self, de: str, ate: str) -> dict[int, int]:
        """Quantas entradas houve em cada hora do dia (0 a 23), entre as datas (AAAA-MM-DD)."""
        linhas = self.conexao.execute(
            """SELECT CAST(strftime('%H', entrada) AS INTEGER) AS hora, COUNT(*) AS total
               FROM acessos WHERE date(entrada) BETWEEN ? AND ?
               GROUP BY hora""",
            (de, ate),
        ).fetchall()
        return {linha["hora"]: linha["total"] for linha in linhas}

    def frequentes(self, de: str, ate: str, limite: int = 10) -> list[tuple[str, str, int]]:
        """Placas que mais entraram no período: (placa, tipo, quantidade de entradas)."""
        linhas = self.conexao.execute(
            f"""SELECT a.placa, COALESCE(v.tipo, '{AVULSO}') AS tipo, COUNT(*) AS total
                FROM acessos a LEFT JOIN veiculos v ON v.placa = a.placa
                WHERE date(a.entrada) BETWEEN ? AND ?
                GROUP BY a.placa ORDER BY total DESC, a.placa LIMIT ?""",
            (de, ate, limite),
        ).fetchall()
        return [(linha["placa"], linha["tipo"], linha["total"]) for linha in linhas]

    def faturamento(self, de: str, ate: str) -> int:
        """Soma dos valores pagos nas saídas do período, em centavos."""
        linha = self.conexao.execute(
            "SELECT COALESCE(SUM(valor), 0) AS total FROM acessos WHERE date(saida) BETWEEN ? AND ?", (de, ate)
        ).fetchone()
        return linha["total"]


def _imprimir(acessos: list[Acesso]) -> None:
    if not acessos:
        print("  (nenhum)")
    for a in acessos:
        saida = a.saida or "ainda dentro"
        dono = f" ({a.proprietario})" if a.proprietario else ""
        horas, minutos = divmod(round(a.minutos), 60)
        valor = f"  pago R$ {a.valor / 100:.2f}".replace(".", ",") if a.valor is not None else ""
        print(f"  {a.placa}  {a.tipo}{dono}  entrada {a.entrada}  saída {saida}  permanência {horas}h{minutos:02d}{valor}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consulta e cadastro do banco do estacionamento. Entradas e saídas: leitor.estacionamento."
    )
    parser.add_argument("--banco", default=str(CAMINHO_PADRAO), help=f"arquivo do banco (padrão: {CAMINHO_PADRAO})")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("cadastrar", help="cadastra mensalista ou bloqueado")
    p.add_argument("placa")
    p.add_argument("proprietario")
    p.add_argument("tipo", choices=[MENSALISTA, BLOQUEADO])
    p.add_argument("--observacao", default="")

    p = sub.add_parser("descadastrar", help="remove um cadastro")
    p.add_argument("placa")

    sub.add_parser("dentro", help="quem está dentro agora?")

    p = sub.add_parser("historico", help="todas as passagens de uma placa e quanto tempo ficou")
    p.add_argument("placa")

    p = sub.add_parser("dia", help="acessos de um dia")
    p.add_argument("data", help="AAAA-MM-DD")

    p = sub.add_parser("limpar", help="LGPD: apaga passagens encerradas há mais de N dias")
    p.add_argument("--dias", type=int, default=90, help="prazo de guarda (padrão: 90)")

    args = parser.parse_args()
    banco = Banco(args.banco)
    try:
        if args.comando == "cadastrar":
            banco.cadastrar(args.placa, args.proprietario, args.tipo, args.observacao)
            print(f"{normalizar(args.placa)} cadastrado como {args.tipo}.")
        elif args.comando == "descadastrar":
            print("Removido." if banco.descadastrar(args.placa) else "Placa não estava cadastrada.")
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
        elif args.comando == "limpar":
            print(f"{banco.apagar_antigos(args.dias)} passagem(ns) com mais de {args.dias} dias apagada(s).")
    except ValueError as erro:
        print(erro, file=sys.stderr)
        return 1
    finally:
        banco.fechar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
