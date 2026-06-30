"""Importa o histórico da planilha "juros por fora" e mostra o resumo.

Uso:
    python scripts/importar_planilha.py "caminho/para/PLANILHA ... AKF.xlsx"
    python scripts/importar_planilha.py "...xlsx" --aba Planilha2 --csv saida.csv

Gera um resumo no terminal e, opcionalmente, exporta os lançamentos
normalizados (com estornos separados dos pagamentos) para um CSV.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gestor_akf.numeros import formatar_valor_br  # noqa: E402
from gestor_akf.passivo import importar_planilha_por_fora  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Importa a planilha de juros por fora.")
    ap.add_argument("planilha", help="Caminho do arquivo .xlsx")
    ap.add_argument("--aba", default="Planilha2", help="Nome da aba (padrão: Planilha2)")
    ap.add_argument("--csv", help="Exporta os lançamentos normalizados para este CSV")
    args = ap.parse_args()

    if not os.path.exists(args.planilha):
        print(f"Arquivo não encontrado: {args.planilha}")
        return 1

    r = importar_planilha_por_fora(args.planilha, aba=args.aba)

    def rs(v):
        return "R$ " + formatar_valor_br(v)

    print("=" * 56)
    print("RESUMO — PASSIVO 'POR FORA'")
    print("=" * 56)
    print(f"Lançamentos lidos:      {r.qtd}")
    print(f"Custo gerado (total):   {rs(r.total_gerado)}")
    print(f"Pago (abatido):         {rs(r.total_pago)}")
    print(f"Estornos/devoluções:    {rs(r.total_estornado)}")
    print(f"SALDO DEVEDOR:          {rs(r.saldo)}")
    print("=" * 56)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Data", "Borderô dentro", "Borderô fora", "Custo",
                        "Pagamento", "Estorno", "Observação"])
            for l in r.lancamentos:
                w.writerow([
                    l.data.isoformat() if l.data else "",
                    l.base01, l.base02,
                    formatar_valor_br(l.valor), formatar_valor_br(l.pagamento),
                    formatar_valor_br(l.estorno), l.observacao,
                ])
        print(f"\nLançamentos exportados para: {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
