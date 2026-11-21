"""Etapa 8: o estacionamento funcionando: entrada com alertas, saída com valor a pagar, lotação e relatórios.

Junta as regras (leitor.regras) com o banco (leitor.banco).
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import date

from leitor import config as cfg
from leitor.banco import CAMINHO_PADRAO, Banco, agora
from leitor.placa import normalizar
from leitor.regras import LIBERADO, Decisao, calcular_valor, decidir_entrada, formatar_reais


@dataclass
class Saida:
    placa: str
    minutos: float
    valor: int
    """Em centavos."""

    @property
    def mensagem(self) -> str:
        horas, minutos = divmod(round(self.minutos), 60)
        return f"{self.placa}: permanência {horas}h{minutos:02d}, valor a pagar {formatar_reais(self.valor)}."


class Estacionamento:
    def __init__(self, banco: Banco, config: cfg.Config):
        self.banco = banco
        self.config = config

    def ocupadas(self) -> int:
        return len(self.banco.dentro_agora())

    def vagas_livres(self) -> int:
        return max(self.config.vagas - self.ocupadas(), 0)

    def vaga_livre(self) -> int | None:
        """A vaga livre de menor número, ou None se o pátio está cheio."""
        ocupadas = self.banco.vagas_ocupadas()
        return next((v for v in range(1, self.config.vagas + 1) if v not in ocupadas), None)

    def entrada(
        self, placa: str, quando: str | None = None, confianca: float | None = None, forcar: bool = False
    ) -> Decisao | None:
        """Carro chegou. Devolve a decisão para a portaria, ou None se ele já estava dentro (leitura repetida).

        Com alerta (bloqueado ou lotado), a cancela fica fechada e nada é gravado. O operador pode
        liberar mesmo assim pelo painel (forcar=True): aí a entrada é gravada, numa vaga se houver.
        """
        if self.banco.acesso_aberto(placa):
            return None
        placa = normalizar(placa)
        decisao = decidir_entrada(placa, self.banco.tipo(placa), self.ocupadas(), self.config.vagas)
        if decisao.situacao != LIBERADO and not forcar:
            return decisao

        vaga = self.vaga_livre()
        self.banco.registrar_entrada(placa, quando, confianca, vaga)
        decisao.registrada = True
        decisao.vaga = vaga
        onde = f"vaga {vaga}" if vaga else "sem vaga livre"
        if decisao.situacao == LIBERADO:
            decisao.mensagem += f" Vaga {vaga}." if vaga else " Sem vaga livre."
        else:
            decisao.mensagem += f" Liberado pelo operador ({onde})."
        return decisao

    def saida(self, placa: str, quando: str | None = None) -> Saida | None:
        """Carro saindo. Calcula e grava o valor. None se não havia entrada em aberto."""
        quando = quando or agora()
        acesso = self.banco.acesso_aberto(placa, referencia=quando)
        if acesso is None:
            return None
        valor = calcular_valor(acesso.minutos, acesso.tipo, self.config.precos)
        self.banco.registrar_saida(placa, quando, valor)
        return Saida(acesso.placa, acesso.minutos, valor)


def imprimir_relatorio(banco: Banco, de: str, ate: str) -> None:
    print(f"Relatório de {de} a {ate}\n")

    print(f"Faturamento: {formatar_reais(banco.faturamento(de, ate))}\n")

    por_hora = banco.entradas_por_hora(de, ate)
    print("Entradas por hora:")
    if not por_hora:
        print("  (nenhuma)")
    maior = max(por_hora.values(), default=0)
    for hora in range(24):
        total = por_hora.get(hora, 0)
        if total:
            pico = "  <- pico" if total == maior else ""
            print(f"  {hora:02d}h  {'#' * total} {total}{pico}")

    print("\nVeículos mais frequentes:")
    frequentes = banco.frequentes(de, ate)
    if not frequentes:
        print("  (nenhum)")
    for placa, tipo, total in frequentes:
        print(f"  {placa}  {tipo:<10}  {total} entrada(s)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Operação do estacionamento: entrada, saída, vagas e relatórios.")
    parser.add_argument("--banco", default=str(CAMINHO_PADRAO), help=f"arquivo do banco (padrão: {CAMINHO_PADRAO})")
    parser.add_argument("--config", default=str(cfg.CAMINHO_PADRAO), help="arquivo de configuração")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("entrada", help="registra uma entrada à mão (se a câmera falhar)")
    p.add_argument("placa")
    p.add_argument("--quando", help="AAAA-MM-DD HH:MM:SS (padrão: agora)")

    p = sub.add_parser("saida", help="registra uma saída à mão e mostra o valor")
    p.add_argument("placa")
    p.add_argument("--quando", help="AAAA-MM-DD HH:MM:SS (padrão: agora)")

    sub.add_parser("vagas", help="ocupação e vagas livres agora")

    hoje = date.today().isoformat()
    p = sub.add_parser("relatorio", help="faturamento, horários de pico e veículos frequentes")
    p.add_argument("--de", default=hoje, help="AAAA-MM-DD (padrão: hoje)")
    p.add_argument("--ate", help="AAAA-MM-DD (padrão: igual a --de)")

    args = parser.parse_args()
    banco = Banco(args.banco)
    estacionamento = Estacionamento(banco, cfg.carregar(args.config))
    try:
        if args.comando == "entrada":
            decisao = estacionamento.entrada(args.placa, args.quando)
            print(decisao.mensagem if decisao else "Essa placa já está dentro.")
        elif args.comando == "saida":
            saida = estacionamento.saida(args.placa, args.quando)
            print(saida.mensagem if saida else "Essa placa não tem entrada em aberto.")
        elif args.comando == "vagas":
            print(f"{estacionamento.ocupadas()} de {estacionamento.config.vagas} vagas ocupadas; "
                  f"{estacionamento.vagas_livres()} livres.")
        elif args.comando == "relatorio":
            imprimir_relatorio(banco, args.de, args.ate or args.de)
    except ValueError as erro:
        print(erro, file=sys.stderr)
        return 1
    finally:
        banco.fechar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
