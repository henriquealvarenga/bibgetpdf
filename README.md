# BibGetPDF

*Da sua bibliografia `.bib` aos PDFs de acesso aberto, automaticamente.*

[![PyPI](https://img.shields.io/pypi/v/bibgetpdf.svg)](https://pypi.org/project/bibgetpdf/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21536833.svg)](https://doi.org/10.5281/zenodo.21536833)
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

📖 **Nunca usou (ou não lembra como)?** O guia passo a passo, do zero até a
pasta de PDFs — incluindo como abrir o Terminal e o que fazer quando algo dá
errado — está em **<https://henriquealvarenga.com/bibgetpdf/#como-usar>**.

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
precisa informar um **e-mail de contato** — e, se quiser, a **chave da API
OpenAlex**.

Você **não precisa editar arquivo nenhum**: o BibGetPDF pergunta e guarda
sozinho. Na pasta onde você vai trabalhar, rode:

```bash
bibgetpdf --init
```

Ele faz duas perguntas no Terminal:

```
   Seu e-mail: voce@exemplo.com

   Chave da API OpenAlex — opcional, tecle Enter para pular.
   Chave [Enter pula]:

✅ Pronto, salvo em: /Users/voce/Bibliografia/bibgetpdf.config
   Não vou perguntar de novo — o arquivo é lido a cada execução.
```

E acabou — **é só desta vez**. As respostas ficam num `bibgetpdf.config`,
lido automaticamente a cada execução seguinte.

> Se você rodar direto (`bibgetpdf --bib refs.bib`) sem ter configurado nada,
> ele pergunta o e-mail na hora, salva e **continua o download no mesmo
> comando** — o `--init` só existe para quem prefere deixar tudo pronto antes.

Os dois valores:

- **`email`** (obrigatório) — qualquer e-mail válido seu. As APIs acadêmicas
  usam para identificar quem está fazendo as requisições (a **Unpaywall
  exige** um); em troca, tratam você com mais tolerância (o chamado _polite
  pool_). Pode ser um alias que encaminhe para o seu e-mail real.
- **`openalex_key`** (opcional) — a chave da API OpenAlex. É **gratuita** e
  leva um minuto: pegue a sua em **<https://openalex.org/settings/api>**.
  Desde **13/02/2026**, sem a chave a fonte OpenAlex fica limitada a ~100
  requisições/dia (as outras 9 fontes continuam funcionando normalmente).
  Para adicioná-la depois, rode `bibgetpdf --init` de novo e responda `s`.

O arquivo é procurado na pasta atual, em `~/.config/bibgetpdf/` e ao lado do
script — nessa ordem. Se preferir editá-lo à mão, o formato é `chave = valor`:

```ini
email = voce@exemplo.com
# openalex_key = sua-chave-openalex
```

*(A partir do código-fonte há também o modelo `bibgetpdf.config.exemplo`,
que pode ser copiado com `cp bibgetpdf.config.exemplo bibgetpdf.config`.)*

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

Dentro da pasta onde ficam o seu `.bib` e os PDFs:

```bash
bibgetpdf --bib references.bib --output PDFs
```

Na primeira vez, ele pergunta o seu e-mail antes de começar (e guarda a
resposta). Das próximas, roda direto.

*(A partir do código-fonte, o equivalente é
`python bibgetpdf.py --bib references.bib --output PDFs`.)*

Opções úteis:

| Flag             | O que faz |
|------------------|-----------|
| `--init`         | Pergunta e-mail/chave e grava o `bibgetpdf.config` (primeiro uso ou alteração) |
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

> Silva, H. A. (2026). *BibGetPDF* (v1.3.0) [Software]. Zenodo.
> https://doi.org/10.5281/zenodo.21796720

Em **BibTeX** (apropriado, já que a ferramenta lê `.bib`):

```bibtex
@software{silva_2026_21796720,
  author       = {Silva, Henrique Alvarenga},
  title        = {BibGetPDF},
  month        = aug,
  year         = 2026,
  publisher    = {Zenodo},
  version      = {v1.3.0},
  doi          = {10.5281/zenodo.21796720},
  url          = {https://doi.org/10.5281/zenodo.21796720},
}
```

**DOI (todas as versões):** [10.5281/zenodo.21536833](https://doi.org/10.5281/zenodo.21536833)
— sempre resolve para a versão mais recente; é o recomendado para citar o
software em geral.

**DOI desta versão (v1.3.0):** [10.5281/zenodo.21796720](https://doi.org/10.5281/zenodo.21796720)
— use quando precisar apontar exatamente a versão empregada na sua pesquisa
(as anteriores: v1.0.0 = `10.5281/zenodo.21536834`, v1.1.0 =
`10.5281/zenodo.21610649`).

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
