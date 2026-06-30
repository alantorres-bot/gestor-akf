# Gestor de Antecipações AKF — Neo Formas

Aplicativo **local** para gerir a antecipação de recebíveis da Neo Formas junto à
AKF Securitizadora: selecionar títulos, ler borderôs, conciliar, controlar o
passivo da diferença "por fora" e medir o custo efetivo real.

> 🔒 **Roda local.** Os PDFs, a planilha e o OCR ficam 100% na sua máquina. A única
> saída para a rede é **opcional**: buscar a carteira direto da API do Consistem
> (ERP da própria Neo Formas). Se preferir, continue usando o export em CSV.

---

## O que o app faz

| Tela | Para que serve |
|------|----------------|
| 📥 **Carteira** | Busca os títulos em aberto **direto da API do Consistem** (ou via export CSV) e separa o que já está na AKF do que está disponível para antecipar. |
| 🎯 **Seleção** | Você diz quanto de caixa precisa; o app sugere os títulos ao **menor custo** (menor prazo primeiro), marcando clientes sem boleto. Sem teto de desconto (o limite da AKF é volátil). |
| ✉️ **Instrução** | Gera o texto do e-mail para André/Kayza com os títulos e as observações corretas. |
| 📄 **Borderôs** | Lê os PDFs escaneados da AKF por **OCR** e **confere a aritmética** de cada um automaticamente. |
| 🔎 **Conciliação** | Cruza o que foi pedido × o que foi operado: NFs não operadas, divergência de valor/vencimento, duplicidade, recompra a conferir. |
| 📊 **Passivo "por fora"** | Importa a planilha de controle, separa estornos dos pagamentos e mostra o saldo devedor. |
| 💰 **Custo efetivo** | Mostra o custo **real** (deságio oficial + parcela "por fora") — quase sempre maior que o aparente. |

---

## Instalação (uma vez só)

Pré-requisito: **Python 3.11+** (testado no 3.13). Para baixar:
<https://www.python.org/downloads/> — na instalação, marque **"Add Python to PATH"**.

Abra o **PowerShell** na pasta do projeto e rode:

```powershell
cd C:\Users\alant\gestor-akf
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

A primeira vez baixa as bibliotecas (inclui o OCR). Depois disso, funciona offline.

---

## Como usar no dia a dia

Sempre que for usar, abra o PowerShell na pasta e rode:

```powershell
cd C:\Users\alant\gestor-akf
.venv\Scripts\activate
streamlit run app.py
```

O app abre sozinho no navegador. Para fechar, volte ao PowerShell e tecle `Ctrl+C`.

Ordem natural de uso: **Carteira → Seleção → Instrução** (antes de operar) e, depois
que a AKF responder, **Borderôs → Conciliação → Passivo → Custo efetivo**.

> **Dica:** em cada tela você pode **enviar o arquivo** (arrastar) **ou** colar o
> **caminho** do arquivo no disco. Os arquivos da AKF ficam em
> `g:\Drives compartilhados\...\BORDEROS\2026\AKF`.

### Lendo borderôs (OCR)
Os borderôs da AKF são imagens escaneadas, então o app usa OCR — leva **~20s por
página**. Cada borderô lido passa por uma **autoconferência**: se
`Total − Deságio ≠ Líquido` ou o desembolso não fechar, aparece um **aviso vermelho**.
Quando tudo bate, aparece "Aritmética confere ✅". Assim nenhum número entra no escuro.

---

## Parâmetros (clientes sem boleto, limites, taxas)

Os ajustes ficam em `config/parametros.json`. Para criar o seu:

1. Copie `config/parametros.exemplo.json` para `config/parametros.json`.
2. Edite com o Bloco de Notas. Principais campos:
   - `clientes_sem_boleto_factoring`: lista de clientes que operam "1 dia após o
     vencimento, sem boleto" (ex.: MIP, MB, Janeiro, Caparaó, House Garden, QRTZ 39).
   - `multa_recompra`: `0.02` = 2%.
   - `taxa_referencia_am`: taxa mensal usada para estimar o deságio na seleção.

   > Os campos `limite_global_akf`, `limite_por_sacado` e `concentracao_maxima_por_sacado`
   > **não barram mais a seleção** — o limite da AKF é volátil. A seleção apenas prioriza
   > pelo menor prazo e soma títulos até o valor-alvo.

Sem esse arquivo, o app usa valores padrão.

---

## Buscar a carteira pela API do Consistem

Na tela 📥 Carteira, o botão **"🔄 Buscar da API do Consistem"** traz os títulos em
aberto direto do ERP (`erp.neoformas.com.br/api`), já com o nome do cliente e a
classificação AKF (portador 998). Elimina a exportação manual do CSV — que continua
disponível como alternativa.

**Configurar o token** (uma vez): use o **mesmo token do NEOControl** (gerado no
programa **CSMEN050 → aba Segurança**, com o serviço **Financeiro** liberado na
**aba Serviço**). Informe-o de uma das duas formas:

```powershell
# opção A — variável de ambiente (vale só na janela atual do PowerShell)
$env:CONSISTEM_API_KEY = "<token>"

# opção B — arquivo local (não vai para o git)
#   crie config\consistem.secret com o token dentro
```

Para mudar a empresa/URL, copie `config/consistem.exemplo.json` para
`config/consistem.json`. O **token nunca é versionado** (`.gitignore` cobre
`config/consistem.secret`).

> Se a API estiver fora do ar ou o serviço não estiver liberado, o app avisa e você
> usa o CSV normalmente.

---

## Importar o histórico da planilha "por fora" (linha de comando)

```powershell
.venv\Scripts\activate
python scripts\importar_planilha.py "CAMINHO\PLANILHA NEO FORMAS CONTROLE JUROS POR FORA - AKF.xlsx"
# opcional: exportar os lançamentos já normalizados (estornos separados)
python scripts\importar_planilha.py "...xlsx" --csv lancamentos.csv
```

---

## Para quem mexe no código

Estrutura:

```
gestor-akf/
├─ app.py                     # interface Streamlit
├─ src/gestor_akf/
│  ├─ numeros.py              # valores em R$ (Decimal, sem erro de float)
│  ├─ util.py                 # datas, normalização de texto
│  ├─ modelos.py              # Borderô e Título
│  ├─ calculos.py             # desembolso, recompra, por fora, custo efetivo
│  ├─ bordero_ocr.py          # PDF escaneado → OCR → dados (com autoconferência)
│  ├─ carteira.py             # importa o CSV do Consistem
│  ├─ consistem_api.py        # busca a carteira ao vivo na API do Consistem
│  ├─ parametros.py           # lê config/parametros.json
│  ├─ selecao.py              # otimização da seleção de títulos
│  ├─ instrucao.py            # gera o e-mail para a AKF
│  ├─ passivo.py              # importa a planilha "por fora"
│  └─ conciliacao.py          # pedido × borderô
├─ scripts/importar_planilha.py
├─ tests/                     # testes (lógica, parsers, API mockada)
└─ config/parametros.exemplo.json
```

Rodar os testes:

```powershell
pytest -m "not ocr and not api"   # rápido — lógica, parsers e API (mockada)
pytest -m "ocr"                   # roda o OCR de verdade sobre um PDF real (~20s)
pytest -m "api"                   # chama a API real (precisa de CONSISTEM_API_KEY)
pytest                            # tudo
```

### Regras de negócio implementadas
- **Desembolso** = Total − Deságio = Líquido − Recompras + Créditos − Débitos − Abatimento.
- **Recompra** = título + correção + **multa 2%** + despesas.
- **"Por fora"** = diferença de valor líquido entre o borderô por dentro
  (PRODUÇÃO, 8xxx) e o por fora (PRODUÇÃO02, 7xxx).
- **Custo efetivo real** = deságio oficial + parcela por fora.
- Clientes sem boleto operam "1 dia após o vencimento, sem boleto".

### Casos de teste de referência (validados contra arquivos reais)
- Borderôs **8585/7104** (29/05/2026): desembolsos 253.962,48 e 238.122,48;
  diferença "por fora" **15.840,00**.
- Planilha de controle: custo gerado 1.451.340,86; pago 1.385.475,51; saldo
  devedor **91.390,64**.

---

## Fora de escopo (por decisão do projeto)

O app **não** gera documentos de locação nem trata de enquadramento fiscal. A
diferença "por fora" é tratada pela sua **substância econômica = custo financeiro**.
Questões fiscais/legais dependem de **parecer profissional** (contador + advogado
tributarista).
