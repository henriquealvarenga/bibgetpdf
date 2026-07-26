# BibGetPDF

*Da sua bibliografia `.bib` aos PDFs de acesso aberto, automaticamente.*

[![PyPI](https://img.shields.io/pypi/v/bibgetpdf.svg)](https://pypi.org/project/bibgetpdf/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21536834.svg)](https://doi.org/10.5281/zenodo.21536834)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

Baixa automaticamente os **PDFs de acesso aberto** dos artigos de um arquivo
`.bib`. Para cada referência, consulta em sequência 10 fontes legítimas de
_open access_ (Unpaywall, Semantic Scholar, OpenAlex, Europe PMC, PMC, arXiv,
CORE, DOAJ, SciELO e, opcionalmente, resolução de DOI por editora), valida se
o que baixou é mesmo um PDF e salva com um nome limpo no padrão
`sobrenome-ano-titulo.pdf`.

Entradas **sem DOI** são o maior motivo de artigos não encontrados (sem DOI,
quase toda fonte fica sem chave de busca). Por isso, antes de baixar, o script
tenta **descobrir o DOI** no Crossref pelo título + sobrenome do 1º autor —
aceitando o resultado só quando ele bate de verdade (título, autor e ano). Com
o DOI preenchido, as 10 fontes voltam a funcionar. (Desligue com
`--no-doi-discovery`.)

Ao final, gera um **relatório HTML de diagnóstico** que classifica o que não
foi baixado (bloqueio anti-bot, paywall real, erro de servidor, host que
bloqueou durante a execução) com links para download manual, e um
**`manifest.csv`** com uma linha por referência (para abrir no Excel).

> Só usa fontes de **acesso aberto**. Não acessa Sci-Hub nem burla paywalls.

---

## Requisitos

- **Python 3.10 ou superior**

## Instalação

Instale com o **pip** (as dependências obrigatórias vêm junto):

```bash
pip install bibgetpdf
```

Para incluir os opcionais recomendados — `unidecode` (nomes de arquivo com
acentos) e `beautifulsoup4` (melhora a extração de PDF de páginas HTML):

```bash
pip install "bibgetpdf[full]"
```

Isso cria o comando **`bibgetpdf`**. *(A partir do código-fonte: clone o
repositório e rode `pip install .`, ou use `python bibgetpdf.py` direto —
nesse caso, instale as dependências com `pip install bibtexparser requests`.)*

---

## Configuração (obrigatória na primeira vez)

O script **não** contém nenhum dado pessoal. Antes do primeiro uso, você
precisa informar dois valores seus: um **e-mail de contato** e a **chave da
API OpenAlex**. A forma mais cômoda é criar um arquivo de credenciais.

### 1. Crie o arquivo `bibgetpdf.config`

Crie um arquivo `bibgetpdf.config` **na pasta onde você vai rodar o comando**
(o BibGetPDF também aceita em `~/.config/bibgetpdf/`). A partir do código-fonte,
dá para copiar o modelo que vem no projeto:

```bash
cp bibgetpdf.config.exemplo bibgetpdf.config
```

### 2. Preencha os dois valores

Abra o `bibgetpdf.config` e edite as duas linhas:

```ini
email = voce@exemplo.com
openalex_key = sua-chave-openalex
```

- **`email`** — qualquer e-mail válido seu. As APIs acadêmicas usam para
  identificar quem está fazendo as requisições (a **Unpaywall exige** um);
  em troca, tratam você com mais tolerância (o chamado _polite pool_). Pode
  ser um alias que encaminhe para o seu e-mail real.
- **`openalex_key`** — a chave da API OpenAlex. É **gratuita** e leva um
  minuto: pegue a sua em **<https://openalex.org/settings/api>**. Desde
  **13/02/2026** ela virou obrigatória — sem a chave, a fonte OpenAlex fica
  limitada a ~100 requisições/dia (as outras 9 fontes continuam funcionando
  normalmente).

Pronto. O script lê esse arquivo automaticamente.

**Sobre o formato das linhas:**

- Os espaços em volta do `=` são livres: `email=x`, `email = x` ou
  `email    =    x` dão no mesmo.
- **Não** é preciso pôr o valor entre aspas nem entre colchetes `{}`. Se por
  hábito do BibTeX você escrever `email = {voce@exemplo.com}`, tudo bem — o
  script ignora as aspas/colchetes das bordas.
- Linhas em branco e linhas começando com `#` são ignoradas (comentários).

### Alternativas ao arquivo

Cada valor pode vir de três lugares, nesta ordem de prioridade —
**linha de comando › variável de ambiente › arquivo**:

| Valor    | Linha de comando   | Variável de ambiente | Arquivo (`bibgetpdf.config`) |
|----------|--------------------|----------------------|------------------------------|
| E-mail   | `--email ...`      | `BIBGETPDF_EMAIL`    | `email = ...`                |
| Chave    | `--openalex-key ...` | `OPENALEX_API_KEY` | `openalex_key = ...`         |

No arquivo, os nomes das chaves aceitam apelidos comuns (ex.: `chave_openalex`
funciona igual a `openalex_key`), mas o recomendado é usar os nomes acima.

---

## Uso

Com o `bibgetpdf.config` pronto, o básico é:

```bash
bibgetpdf --bib references.bib --output PDFs
```

*(A partir do código-fonte, o equivalente é
`python bibgetpdf.py --bib references.bib --output PDFs`.)*

Opções úteis:

| Flag             | O que faz |
|------------------|-----------|
| `--bib`          | Arquivo `.bib` de entrada (padrão: `references.bib`) |
| `--output`       | Pasta onde salvar os PDFs (padrão: `PDFs`) |
| `--threshold`    | Rigor da comparação de títulos, 0–1 (padrão: `0.75`; maior = mais estrito) |
| `--delay`        | Pausa em segundos entre artigos (padrão: `3.0`; aumente se já foi bloqueado) |
| `--doi-scrape`   | Reativa a fonte que raspa páginas de editora (mais cobertura, mais risco de bloqueio; desligada por padrão) |
| `--no-doi-discovery`   | Não descobrir DOI no Crossref para entradas sem DOI (ver abaixo; ligada por padrão) |
| `--use-doi-as-filename` | Nomear cada PDF pelo DOI (único) em vez de `sobrenome-ano-titulo` — útil para títulos ambíguos |
| `--no-report`    | Não gerar o relatório HTML |
| `--no-probe`     | No diagnóstico, não fazer requisições extras (classifica offline) |

Veja todas com `bibgetpdf --help`.

---

## O que é gerado

Dentro da pasta de saída (`PDFs/` por padrão):

- Os **PDFs** baixados, nomeados `sobrenome-ano-titulo.pdf` (ou pelo DOI, com
  `--use-doi-as-filename`).
- **`relatorio.html`** — diagnóstico visual do que não baixou, com links para
  baixar manualmente (abra no navegador).
- **`manifest.csv`** — uma linha por referência: status, fonte, DOI (marcando
  os que foram descobertos no Crossref), motivo da falha. Abre no Excel/
  LibreOffice para revisar o lote de uma vez.
- **`download_log.txt`** — log detalhado da execução.

O resume é automático: rodar de novo pula o que já foi baixado (revalidando
cada PDF; arquivos corrompidos são baixados de novo).

---

## Fluxo recomendado

Para bibliografias grandes, rende mais combinar com o Zotero:

1. No Zotero, use **"Find Available PDFs"** para pegar o que ele já resolve.
2. Exporte como `.bib` **apenas** as referências que ficaram sem PDF.
3. Rode este script nesse `.bib` reduzido.

Artigos que sobrarem em paywall real podem ser baixados pelo login
institucional via **Portal CAPES/CAFe** (<https://periodicos.capes.gov.br>) —
o relatório HTML já traz os links prontos.

---

## Segurança das credenciais

O arquivo `bibgetpdf.config` contém a sua chave de API — **não compartilhe e
não versione**. O `.gitignore` do projeto já ignora esse arquivo; o que pode
ir para um repositório é o `bibgetpdf.config.exemplo` (só com placeholders).

---

## Licença

Distribuído sob a licença **MIT** — veja o arquivo [LICENSE](LICENSE). Você pode
usar, modificar e redistribuir livremente, mantendo o aviso de copyright.

---

## Como citar

Se este software foi útil na sua pesquisa, por favor cite-o:

> Silva, H. A. (2026). *BibGetPDF* (v1.0.0) [Software]. Zenodo.
> https://doi.org/10.5281/zenodo.21536834

Em **BibTeX** (apropriado, já que a ferramenta lê `.bib`):

```bibtex
@software{silva_2026_21536834,
  author       = {Silva, Henrique Alvarenga},
  title        = {BibGetPDF},
  month        = jul,
  year         = 2026,
  publisher    = {Zenodo},
  version      = {v1.0.0},
  doi          = {10.5281/zenodo.21536834},
  url          = {https://doi.org/10.5281/zenodo.21536834},
}
```

**DOI (todas as versões):** [10.5281/zenodo.21536834](https://doi.org/10.5281/zenodo.21536834)

O GitHub também exibe um botão **"Cite this repository"** (gerado a partir do
`CITATION.cff`) com o formato pronto em APA e BibTeX.

---

## Autor

**Dr. Henrique Alvarenga** — médico psiquiatra e professor do curso de Medicina
da Universidade Federal de São João del-Rei (UFSJ), onde coordena as disciplinas
de Psicopatologia e Psiquiatria. Atua na interface entre ciência, tecnologia,
filosofia, comportamento e emoção, com interesse em análise de dados (R e
Python) — terreno de onde nasceu esta ferramenta.

🔗 [github.com/henriquealvarenga](https://github.com/henriquealvarenga)

---

Construído com o apoio do **[Claude Code](https://claude.com/claude-code)** (Anthropic).
