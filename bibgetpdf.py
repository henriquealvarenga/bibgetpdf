"""
BibFix - Download de PDFs v8 (arquivo: bibgetpdf.py)
===========================================================
Script para download automatizado de artigos acadêmicos em formato PDF
a partir de um arquivo de referências bibliográficas (.bib).

O script consulta 10 fontes de acesso aberto em sequência:
  1. Unpaywall       — maior base global de open access
  2. Semantic Scholar — API do Allen Institute for AI
  3. OpenAlex        — base aberta de metadados acadêmicos
  4. Europe PMC      — REST API direta do Europe PubMed Central
  5. PMC             — PubMed Central via NCBI E-utilities (fallback)
  6. arXiv           — preprints de CS, física, matemática, biologia
  7. CORE            — agregador de repositórios institucionais
  8. DOAJ            — Directory of Open Access Journals
  9. DOI-PDF         — resolução de DOI + padrões por editora
  10. SciELO          — periódicos latino-americanos

[v8] Antes de consultar as 10 fontes, entradas SEM DOI passam por uma etapa
de DESCOBERTA DE DOI no Crossref (busca por título + sobrenome do 1º autor).
Sem DOI, quase todas as fontes falham; com o DOI preenchido, todas voltam a
funcionar. É a maior lacuna de cobertura identificada na análise de bibliotecas
(2026-07-23). Ligada por padrão; desligue com --no-doi-discovery.

Melhorias na v8 (em relação à v7):
  - Descoberta de DOI via Crossref (try_crossref_doi) para entradas sem DOI:
    consulta api.crossref.org/works por título (query.bibliographic) +
    sobrenome (query.author) e só ACEITA o DOI com match validado pelo nosso
    código — título fuzzy ≥ threshold, sobrenome do 1º autor e ano dentro de
    ±1. O campo `score` do Crossref NÃO é confiança: nos testes, mirrors
    'posted-content' de 2025 do "Attention is all you need" pontuavam no topo;
    a validação de ano os rejeita. Um DOI errado é pior que nenhum (levaria a
    baixar o PDF de outro artigo), então a etapa erra para o lado de não achar.
  - Sobrenome do 1º autor via bibtexparser.customization.splitname (regras
    von/Last/Jr), substituindo o antigo author.split(" and ")[0] ingênuo —
    usado no nome do arquivo, no diagnóstico e na busca por autor do Crossref.
  - Manifesto CSV do lote (manifest.csv na pasta de saída): uma linha por
    entrada com status, fonte, DOI (marcando os descobertos), motivo — abre
    direto no Excel/LibreOffice para revisar o que faltou.
  - --use-doi-as-filename: nomeia o arquivo pelo DOI (único) em vez de
    Sobrenome-Ano-Titulo, útil quando os títulos são ambíguos/repetidos.
  - Nota: a busca por título na Unpaywall (/v2/search) foi avaliada e
    DESCARTADA — o endpoint responde HTTP 500 mesmo com e-mail válido (testado
    em 2026-07-24). A descoberta de DOI via Crossref já alimenta o caminho
    Unpaywall por DOI, que é o confiável, tornando a busca por título redundante.
  - Zero dependência nova (csv e splitname já vêm com stdlib/bibtexparser).

Melhorias na v7 (em relação à v6) — correções da revisão de código:
  - Circuit breaker atribui o bloqueio ao host CERTO: a v6 marcava o host
    da URL pedida, mas com redirects (doi.org → editora) o 403 vinha do
    destino final — um 403 da Elsevier bloqueava o doi.org inteiro e
    matava a resolução de DOI pelo resto da execução. Agora o host
    penalizado é o da resposta final, cada hop do redirect entra no
    controle de intervalo, e resolvedores (doi.org) nunca são bloqueados.
  - Circuit breaker com 3 strikes: um único 403 costuma ser da URL
    específica (padrão adivinhado errado, artigo com paywall), não do IP.
    Editoras agora só são desativadas após 3 respostas 429/403.
  - 429 em API acadêmica espera o Retry-After (com teto) e tenta 1 vez de
    novo, em vez de matar a fonte pela execução inteira. Retry-After em
    formato HTTP-date também é aceito.
  - UA dividido de novo (como na v5): APIs recebem o UA acadêmico honesto;
    downloads de editora voltam ao UA de navegador — Cloudflare/Akamai dão
    403 imediato a UA não-navegador, e cada 403 desses alimentava o
    circuit breaker da v6, piorando exatamente o que ela queria resolver.
  - SciELO só resolve o DOI via doi.org quando ele aparenta ser SciELO
    (prefixo 10.1590/... ou "scielo" no texto) — antes TODA entrada com
    DOI gerava um acesso à landing page da editora, mesmo sem --doi-scrape.
  - Três níveis de intervalo: API 1s, repositório (arXiv, Europe PMC,
    SciELO) 2s, editora 6s — com jitter, para não parecer metrônomo.
  - Download atômico: baixa para .part e renomeia só após validar; o
    resume revalida PDFs existentes (arquivo corrompido era pulado para
    sempre); validação de %%EOF sem a tolerância que aceitava truncados.
  - Retry para erros transitórios (429/500/502/503/504), não só timeout.
  - Corpo baixado em streaming com teto incremental (a v6 declarava
    stream=True mas carregava tudo na RAM antes de checar o tamanho).
  - Relatório HTML com escaping (título com < ou & quebrava a página),
    categoria própria para "host bloqueou durante a execução", e a lista
    de hosts bloqueados agora aparece no HTML e no download_log.txt.
  - Diagnóstico reaproveita o motivo já registrado quando possível;
    --no-probe desliga as requisições extras de diagnóstico.
  - Extração de PDF de HTML: padrões genéricos (/pdf/ e .pdf em <a>) só
    aceitam links do MESMO host da página — o primeiro link de outro host
    podia baixar o artigo errado e salvá-lo com o nome do artigo certo.
  - --threshold agora vale também para Europe PMC e SciELO (era ignorado).
  - Limpeza: polite_get lança HostBlockedError em vez de retornar None
    (elimina 17 blocos repetidos), _resolve_url usa urljoin (RFC 3986),
    campos mortos removidos (UA sem uso, Config.max_pdf_size), validação
    de --threshold/--delay.

Melhorias na v6 (em relação à v5) — foco em não ser bloqueado:
  - User-agent honesto: a v5 fingia ser Chrome no macOS para downloads
    diretos. Baixar 200 PDFs sequenciais sem carregar CSS/JS é o padrão que
    dispara detecção de bot em Elsevier, Wiley e MDPI. Agora usa um UA
    acadêmico identificado, com e-mail de contato.
  - Rate limit POR DOMÍNIO (polite_get): a v5 pausava 1.5s entre artigos,
    mas cada artigo percorre até 10 fontes — logo, até 10 requisições em
    menos de um segundo. Agora o intervalo mínimo é rastreado por host:
    1s para APIs acadêmicas, 6s para editoras comerciais.
  - Circuit breaker: host que responde 429/403 é desativado pelo resto da
    execução (respeitando Retry-After). Insistir num host que já bloqueou
    é o que transforma bloqueio temporário em permanente.
  - Fonte DOI-PDF desligada por padrão: era a etapa que raspava landing
    pages de editora com 28 padrões de URL, principal causa de bloqueio de
    IP. Reative com --doi-scrape se quiser os poucos PDFs a mais.
  - --delay para ajustar a pausa entre artigos (default 3.0s).
  - Relatório final lista os hosts que bloquearam durante a execução.

Fluxo recomendado: rode o "Find Available PDFs" do Zotero primeiro, exporte
como .bib apenas o que sobrou, e só então rode este script no .bib reduzido.

Melhorias na v5 (em relação à v4):
  - Relatório HTML de diagnóstico gerado ao final de cada execução:
      * Classifica automaticamente o motivo da falha de cada artigo:
        "OA bloqueado por bot (MDPI, Elsevier...)" — links diretos para
        download manual imediato
        "Paywall real" — links para o Portal CAPES/CAFe
        "Erro de servidor / URL expirada"
      * Abre facilmente no navegador com a pasta de PDFs
  - find_and_download: expõe URL final resolvida (useful para diagnóstico)
  - --no-report: opção para desabilitar geração do HTML

Uso:
    python bibgetpdf.py --bib refs.bib --output PDFs --email voce@email.com
    python bibgetpdf.py --bib refs.bib --delay 5        # mais conservador
    python bibgetpdf.py --bib refs.bib --doi-scrape     # reativa DOI-PDF
    python bibgetpdf.py --bib refs.bib --threshold 0.80
    python bibgetpdf.py --bib refs.bib --no-report
    python bibgetpdf.py --bib refs.bib --no-probe       # diagnóstico offline
    python bibgetpdf.py --bib refs.bib --no-doi-discovery      # [v8] não busca DOI no Crossref
    python bibgetpdf.py --bib refs.bib --use-doi-as-filename   # [v8] arquivo nomeado pelo DOI

Configuração pessoal (e-mail de contato + chave OpenAlex):
  O fonte NÃO contém dados pessoais. Cada valor é resolvido nesta ordem —
  flag na linha de comando > variável de ambiente > arquivo de credenciais:

    e-mail:  --email voce@exemplo.com  |  BIBGETPDF_EMAIL  |  arquivo (email=)
    chave:   --openalex-key sua-chave  |  OPENALEX_API_KEY |  arquivo (openalex_key=)

  Jeito mais cômodo — criar um arquivo 'bibgetpdf.config' na pasta do script
  (copie de bibgetpdf.config.exemplo):

    email = voce@exemplo.com
    openalex_key = sua-chave-openalex

  A chave OpenAlex é gratuita (openalex.org/settings/api) e virou obrigatória
  em 13/02/2026 — sem ela, a fonte OpenAlex fica limitada a ~100 req/dia.
  A Unpaywall exige um e-mail de contato válido. Se versionar a pasta com
  git, ponha 'bibgetpdf.config' no .gitignore.

Dependências obrigatórias:
    pip install bibtexparser requests

Dependências opcionais:
    pip install unidecode      (melhora sanitização de nomes com acentos)
    pip install beautifulsoup4 (melhora extração de PDF de landing pages HTML)
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import csv             # [v8] manifesto CSV do lote (o que baixou/faltou)
import html            # [v7] escaping de campos do .bib no relatório HTML
import os              # [v7] ler OPENALEX_API_KEY do ambiente
import random          # [v7] jitter no intervalo entre requisições
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict        # [v7] movido do meio do arquivo
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime  # [v7] Retry-After em HTTP-date
from pathlib import Path
from urllib.parse import urljoin, urlparse     # [v7] urljoin p/ _resolve_url

# --- Dependências externas (com fallback gracioso) ---

try:
    import bibtexparser
    from bibtexparser.bparser import BibTexParser
    from bibtexparser.customization import convert_to_unicode
    # [v8] splitname: parser de nomes do próprio bibtexparser (sem dep nova),
    # usado para extrair o sobrenome do 1º autor respeitando as regras do
    # BibTeX (von/Last/Jr/First) em vez do antigo author.split(" and ")[0].
    from bibtexparser.customization import splitname
except ImportError:
    sys.exit("❌ Instale: pip install bibtexparser")

try:
    import requests
except ImportError:
    sys.exit("❌ Instale: pip install requests")

# unidecode: opcional
try:
    from unidecode import unidecode
except ImportError:
    unidecode = None
    print("⚠️  'unidecode' não instalado (opcional).\n")

# beautifulsoup4: opcional — melhora extração de PDF de páginas HTML
try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False


# ============================================================================
# SESSÕES HTTP
# ============================================================================
# Duas sessões separadas:
#   SESSION:     para downloads diretos (simula navegador)
#   API_SESSION: para APIs acadêmicas (identifica a ferramenta)

# [v7] Sem e-mail pessoal embutido: o mailto começa com um placeholder e é
# reescrito em runtime (main) com o e-mail que o usuário configurar. Assim o
# fonte não carrega dado pessoal de ninguém e pode ser compartilhado.
UA_ACADEMIC = "BibFix/8.0 (academic PDF downloader; mailto:seu.email@exemplo.com)"
UA_BROWSER = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

SESSION = requests.Session()
SESSION.headers.update({
    # [v7] De volta ao UA de navegador para downloads diretos (a divisão da
    # v5). A v6 usou o UA acadêmico aqui também, por honestidade — mas
    # Cloudflare/Akamai respondem 403 imediato a qualquer UA não-navegador,
    # antes mesmo de avaliar o comportamento. Cada 403 desses alimentava o
    # circuit breaker e derrubava hosts que serviriam o PDF numa boa.
    # A honestidade fica onde é recompensada: API_SESSION (abaixo) continua
    # se identificando como BibFix, com e-mail de contato.
    "User-Agent": UA_BROWSER,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "application/pdf;q=0.8,*/*;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
})

API_SESSION = requests.Session()
API_SESSION.headers.update({
    "User-Agent": UA_ACADEMIC,
    "Accept": "application/json",
})


# ============================================================================
# [v6] RATE LIMITING POR DOMÍNIO — [v7] reescrito
# ============================================================================
# O problema da v5: o sleep de 1.5s ficava no loop principal, entre *artigos*.
# Como cada artigo percorre até 10 fontes, um único artigo podia gerar 10
# requisições em menos de um segundo. E se 40 entradas do .bib fossem da mesma
# editora, ela levava 40 acessos quase seguidos.
#
# A correção rastreia o último acesso por host e garante intervalo mínimo.
#
# [v7] Três mudanças estruturais em relação à v6:
#   1. O host penalizado por 429/403 é o da RESPOSTA FINAL (r.url), não o da
#      URL pedida. Com allow_redirects=True, um 403 da Elsevier chegava numa
#      requisição feita ao doi.org — e a v6 bloqueava o doi.org inteiro,
#      matando a resolução de DOI pelo resto da execução. Cada hop do
#      redirect também entra agora no _last_hit; sem isso, o intervalo de 6s
#      nunca era aplicado ao host que de fato atendeu a requisição.
#   2. Circuit breaker com strikes: 403 é frequentemente da URL específica
#      (padrão de URL adivinhado errado, artigo com paywall), não do IP.
#      Editoras só são desativadas após STRIKES_TO_BLOCK respostas 429/403.
#      APIs sinalizam cota/chave: 429 espera o Retry-After e repete 1 vez;
#      403 desativa a fonte na hora (condição estável, sem alarme).
#   3. polite_get LANÇA HostBlockedError em vez de retornar None — o antigo
#      contrato exigia "if r is None: raise ..." em todos os 17 call sites.

_last_hit: dict[str, float] = defaultdict(float)

# [v7] Hosts só de API (JSON/XML, feitos para consumo programático): 1s.
# www.ncbi.nlm.nih.gov entrou — a API idconv da fonte PMC mora lá e estava
# levando 6s de intervalo por engano.
# [v8] api.crossref.org voltou: a descoberta de DOI (try_crossref_doi) o
# consulta. É API pura (JSON), então merece o intervalo de 1s como as demais.
API_HOSTS = (
    "api.unpaywall.org", "api.semanticscholar.org", "api.openalex.org",
    "www.ebi.ac.uk", "eutils.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov",
    "export.arxiv.org", "api.core.ac.uk", "doaj.org", "search.scielo.org",
    "api.crossref.org",  # [v8] descoberta de DOI
)

# [v7] Repositórios OA que também SERVEM PDFs: intervalo próprio de 2s.
# Na v6 estavam junto das APIs, com dois efeitos ruins: 1s de intervalo para
# download de PDF, e um bloqueio real deles era reportado como "cota de API"
# e sumia da lista final de hosts que bloquearam.
REPOSITORY_HOSTS = (
    "arxiv.org", "europepmc.org", "www.scielo.br",
)

# [v7] Resolvedores de DOI NUNCA entram no circuit breaker: com redirects,
# um 4xx atribuído a eles é sempre do destino final, não do resolvedor.
RESOLVER_HOSTS = ("doi.org", "dx.doi.org")

INTERVAL_API = 1.0         # segundos entre acessos ao mesmo host de API
INTERVAL_REPOSITORY = 2.0  # [v7] repositórios OA que servem PDF
INTERVAL_PUBLISHER = 6.0   # editoras comerciais
MAX_BACKOFF = 300          # teto (s) para honrar o Retry-After
API_RETRY_MAX_WAIT = 30.0  # [v7] espera máxima in-loco num 429 de API
STRIKES_TO_BLOCK = 3       # [v7] 429/403 numa editora antes de desativá-la

# Hosts desativados nesta execução (após os strikes) — pulados sem tráfego.
_blocked_hosts: set[str] = set()

# [v6] Subconjunto: APIs com 403/429 persistente por cota/chave, não por
# bloqueio de IP. Reportadas separadamente, sem alarme.
_api_unavailable: set[str] = set()

# [v7] Contagem de 429/403 por host (editoras/repositórios).
_strikes: dict[str, int] = defaultdict(int)


class HostBlockedError(requests.RequestException):
    """[v7] Lançada por polite_get quando o host já foi desativado nesta
    execução. Herda de RequestException de propósito: todos os call sites
    que já tratavam falha de rede tratam o bloqueio do mesmo jeito, sem
    precisar de código novo."""


def _host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _interval_for(host: str) -> float:
    if host in API_HOSTS:
        return INTERVAL_API
    if host in REPOSITORY_HOSTS:  # [v7]
        return INTERVAL_REPOSITORY
    return INTERVAL_PUBLISHER


def _host_rank(url: str) -> int:
    """[v7] Classifica o risco do host de uma URL candidata: API (0),
    repositório OA (1), editora/desconhecido (2). Usado em find_and_download
    para tentar primeiro as URLs com menos chance de 403 — o Unpaywall, por
    exemplo, costuma listar a URL da editora antes da do repositório."""
    host = _host_of(url)
    if host in API_HOSTS:
        return 0
    if host in REPOSITORY_HOSTS:
        return 1
    return 2


def _parse_retry_after(value: str | None) -> float | None:
    """[v7] Interpreta o header Retry-After nos DOIS formatos da RFC 9110:
    delta em segundos ("120") ou HTTP-date ("Wed, 21 Oct 2026 07:28:00 GMT").
    A v6 só aceitava o inteiro — o formato data caía num fallback de 60s.

    Returns:
        Segundos de espera (limitado a MAX_BACKOFF), ou None se o header
        estiver ausente/ilegível.
    """
    if not value:
        return None
    try:
        return min(float(int(value)), float(MAX_BACKOFF))
    except (TypeError, ValueError):
        pass
    try:
        dt = parsedate_to_datetime(value)
        secs = (dt - datetime.now(dt.tzinfo)).total_seconds()
        return min(max(secs, 0.0), float(MAX_BACKOFF))
    except Exception:
        return None


def polite_get_API(url: str, **kwargs):
    """[v6] Atalho para polite_get usando a sessão de APIs acadêmicas."""
    return polite_get(url, session=API_SESSION, **kwargs)


def polite_get(url: str, session: requests.Session | None = None,
               _retried_429: bool = False, **kwargs):
    """
    [v6] GET com intervalo mínimo por domínio e circuit breaker.
    [v7] Reescrita — o racional completo está no comentário da seção. Resumo:

      - Espera o intervalo do host com jitter de até +50% (intervalo exato
        de 6.000s a cada request é assinatura de automação).
      - Registra _last_hit para CADA host da cadeia de redirect.
      - Penaliza 429/403 no host da resposta FINAL (r.url):
          * resolvedor (doi.org)  → nunca bloqueia;
          * API: 429 → espera Retry-After (teto API_RETRY_MAX_WAIT) e repete
            1 vez; se persistir — ou num 403 — desativa a fonte
            (_api_unavailable), porque cota/chave é condição estável;
          * editora/repositório → strike; desativa após STRIKES_TO_BLOCK.

    Args:
        url:          URL para o GET
        session:      SESSION (downloads) ou API_SESSION; default SESSION
        _retried_429: uso interno — marca que o retry de 429 já foi feito

    Raises:
        HostBlockedError: o host pedido já está desativado nesta execução.

    Returns:
        requests.Response — nunca None (diferença da v6).
    """
    if session is None:
        session = SESSION

    host = _host_of(url)

    if host in _blocked_hosts:
        raise HostBlockedError(f"{host} desativado nesta execução")

    # [v7] Espera com jitter: alvo = intervalo × [1.0, 1.5)
    target = _interval_for(host) * random.uniform(1.0, 1.5)
    elapsed = time.time() - _last_hit[host]
    if elapsed < target:
        time.sleep(target - elapsed)

    try:
        r = session.get(url, **kwargs)
    finally:
        _last_hit[host] = time.time()

    # [v7] Registrar cada hop do redirect: o host que atendeu de verdade
    # também precisa entrar no controle de intervalo.
    for resp in list(r.history) + [r]:
        hop = _host_of(resp.url)
        if hop:
            _last_hit[hop] = time.time()

    if r.status_code in (429, 403):
        final_host = _host_of(r.url) or host  # [v7] quem respondeu de fato

        if final_host in RESOLVER_HOSTS:
            # [v7] 4xx "no doi.org" é do destino do redirect (ou soluço do
            # resolvedor) — penalizar aqui mataria TODA resolução de DOI.
            return r

        wait = _parse_retry_after(r.headers.get("Retry-After"))

        if final_host in API_HOSTS:
            if r.status_code == 429 and not _retried_429:
                # [v7] 429 é transitório por definição: honrar o Retry-After
                # (com teto) e repetir uma única vez, em vez de matar a
                # fonte pela execução inteira como fazia a v6.
                pause = min(wait if wait is not None else 5.0, API_RETRY_MAX_WAIT)
                print(f"\n     ⏳ {final_host}: 429 — aguardando {pause:.0f}s "
                      f"(Retry-After) e tentando de novo")
                r.close()
                time.sleep(pause)
                return polite_get(url, session=session, _retried_429=True, **kwargs)
            _blocked_hosts.add(final_host)
            _api_unavailable.add(final_host)
            print(f"\n     ⓘ  {final_host}: {r.status_code} (cota anônima ou "
                  f"chave necessária) — fonte pulada nesta execução")
        else:
            # [v7] Editora/repositório: strikes antes de desativar — um 403
            # isolado costuma ser da URL (padrão errado, artigo específico
            # pago), não do IP inteiro. Insistir num host que já deu vários
            # é o que transforma bloqueio temporário em permanente.
            _strikes[final_host] += 1
            if _strikes[final_host] >= STRIKES_TO_BLOCK:
                _blocked_hosts.add(final_host)
                print(f"\n     ⛔ {final_host}: {r.status_code} pela "
                      f"{_strikes[final_host]}ª vez — host desativado nesta "
                      f"execução (Retry-After: "
                      f"{r.headers.get('Retry-After') or 'ausente'})")
            else:
                print(f"\n     ⚠️  {final_host}: {r.status_code} "
                      f"(strike {_strikes[final_host]}/{STRIKES_TO_BLOCK})")

    return r


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

@dataclass(frozen=True)
class Config:
    """Configuração imutável passada para todas as funções.

    Substitui variáveis globais mutáveis, tornando o código testável
    e thread-safe (sem estado compartilhado entre workers).
    """
    email: str
    # [v7] max_pdf_size saiu: era campo morto — download_file sempre usou o
    # global MAX_PDF_SIZE. Um limite, um só lugar.
    title_match_threshold: float = 0.75
    # [v6] A fonte "DOI-PDF" raspa landing pages de editora aplicando 28
    # padrões de URL. É a etapa que mais gera tráfego indesejado em domínios
    # comerciais e a principal causa de bloqueio de IP. Desligada por padrão.
    enable_doi_scrape: bool = False
    # [v6] Pausa entre artigos no loop principal.
    delay_between_entries: float = 3.0
    # [v7] O diagnóstico do relatório faz ~1 requisição extra por artigo que
    # falhou; --no-probe desliga isso e classifica só pelo motivo registrado.
    probe_failures: bool = True
    # [v7] Chave da API OpenAlex. Desde 13/02/2026 a OpenAlex exige uma key
    # (gratuita, em openalex.org/settings/api) para praticamente toda
    # chamada — sem ela o teto é ~100 requisições/dia, insuficiente para um
    # .bib grande. Fica vazia por padrão; preenchida por --openalex-key ou
    # pela variável de ambiente OPENALEX_API_KEY. Vazia = comportamento
    # antigo (só mailto), que já bate no limite de cota anônima.
    openalex_api_key: str = ""
    # [v8] Descoberta de DOI no Crossref para entradas sem DOI. Ligada por
    # padrão — é a maior alavanca de cobertura (sem DOI, quase toda fonte
    # falha). Desligue com --no-doi-discovery se quiser evitar as chamadas
    # extras ao Crossref (1 por entrada sem DOI).
    enable_doi_discovery: bool = True
    # [v8] Nomear o arquivo pelo DOI (ex.: 10.1016_s0022-2836...pdf) em vez de
    # Sobrenome-Ano-Titulo. Útil quando há títulos ambíguos/repetidos. Entradas
    # sem DOI (nem descoberto) caem no padrão Sobrenome-Ano-Titulo mesmo assim.
    use_doi_as_filename: bool = False


DEFAULT_BIB_INPUT = "references.bib"
DEFAULT_PDF_DIR = "PDFs"
# [v7] Placeholder, NÃO um e-mail real. Se o script rodar com este valor
# (ninguém configurou nada), o main avisa e sai. Configure o seu e-mail por
# --email, pela variável de ambiente BIBGETPDF_EMAIL, ou no arquivo de config.
DEFAULT_EMAIL = "seu.email@exemplo.com"
# [v7] Arquivo de credenciais local (ao lado deste script) com os dados
# PESSOAIS de quem roda — e-mail de contato e chave da OpenAlex — mantidos
# FORA do código, para o script poder ser compartilhado sem editar o fonte.
# Formato: uma linha "chave = valor" por item; linhas em branco e começando
# com # são ignoradas. Chaves reconhecidas: email, openalex_key.
# Precedência de cada valor: flag na linha de comando > variável de ambiente
# > este arquivo. Modelo pronto para copiar em bibgetpdf.config.exemplo.
# Se um dia versionar a pasta com git, ponha este arquivo no .gitignore.
CONFIG_FILE = "bibgetpdf.config"

# [v7] Apelidos aceitos no arquivo de config → nome canônico. Tolera as
# grafias mais prováveis (PT/EN, hífen/underscore) para o arquivo não falhar
# calado por um nome ligeiramente diferente — ex.: alguém escreve
# "chave_openalex" em vez de "openalex_key". Chaves não listadas são mantidas
# como estão (minúsculas).
_CONFIG_KEY_ALIASES = {
    # → email
    "email": "email", "e-mail": "email", "e_mail": "email",
    "mail": "email", "contato": "email", "email_contato": "email",
    # → openalex_key
    "openalex_key": "openalex_key", "openalex-key": "openalex_key",
    "openalexkey": "openalex_key", "openalex": "openalex_key",
    "chave_openalex": "openalex_key", "chave-openalex": "openalex_key",
    "chave_api_openalex": "openalex_key", "chave": "openalex_key",
    "api_key": "openalex_key", "apikey": "openalex_key",
}
MAX_PDF_SIZE = 100 * 1024 * 1024  # usado em download_file (acesso global)


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================


def load_bib(filepath: str) -> bibtexparser.bibdatabase.BibDatabase:
    """Carrega e parseia um arquivo BibTeX (.bib)."""
    text = Path(filepath).read_text(encoding="utf-8", errors="replace")
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    parser.ignore_nonstandard_types = False
    return bibtexparser.loads(text, parser=parser)


def sanitize(text: str) -> str:
    """Sanitiza texto para uso seguro em nomes de arquivo (max 80 chars)."""
    if unidecode:
        text = unidecode(text)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:80]


def _first_author_surname(author_field: str) -> str:
    """[v8] Sobrenome do 1º autor via bibtexparser.customization.splitname.

    Substitui o antigo author.split(" and ")[0] + heurística de vírgula, que
    tratava mal nomes com partícula (von/van/de) e 'Sobrenome, Nome'. splitname
    aplica as regras do BibTeX (First / von / Last / Jr); juntamos von+last
    para preservar 'von Neumann', 'García Márquez'. Em entrada malformada
    (chaves desbalanceadas) splitname pode lançar — aí caímos na heurística
    antiga. Retorna "" quando não há autor.
    """
    if not author_field or not author_field.strip():
        return ""
    first = author_field.split(" and ")[0].strip()
    if not first:
        return ""
    try:
        parts = splitname(first)
    except Exception:
        parts = None
    if parts:
        surname = " ".join((parts.get("von") or []) + (parts.get("last") or [])).strip()
        if surname:
            return surname
    # Fallback: heurística da v7 (splitname indisponível ou nome atípico).
    if "," in first:
        return first.split(",")[0].strip()
    toks = first.split()
    return toks[-1] if toks else ""


def _entry_year(entry: dict) -> int | None:
    """[v8] Ano da entrada como int (1º grupo de 4 dígitos), ou None. Tolera
    '{1990}', '2018a', 'in press' (→ None), intervalos '1999--2000', etc."""
    m = re.search(r"\d{4}", entry.get("year", "") or "")
    return int(m.group()) if m else None


def make_filename(entry: dict, use_doi: bool = False) -> str:
    """Gera nome de arquivo. Padrão: Sobrenome-Ano-Titulo.pdf.

    [v8] use_doi=True nomeia pelo DOI (URL-safe), garantidamente único, quando
    a entrada tem DOI (inclusive um descoberto no Crossref); sem DOI utilizável,
    cai no padrão Sobrenome-Ano-Titulo. [v8] o sobrenome agora vem de splitname.
    """
    if use_doi:
        doi = clean_doi(entry.get("doi", "")) if entry.get("doi") else ""
        if doi:
            # DOI tem '/', '(', ')', etc.: troca tudo fora de [\w.-] por '_'.
            safe = re.sub(r"[^\w.-]+", "_", doi).strip("_")
            if safe:
                return f"{safe}.pdf"
        # sem DOI utilizável → segue para o padrão Sobrenome-Ano-Titulo.
    surname = _first_author_surname(entry.get("author", "")) or "Unknown"
    year = (entry.get("year") or "0000").strip() or "0000"
    title = entry.get("title", "untitled").strip().replace("{", "").replace("}", "")
    return f"{sanitize(surname)}-{year}-{sanitize(title)}.pdf"


def clean_doi(doi: str) -> str:
    """Remove prefixos de URL de um DOI (ex: https://doi.org/10.x → 10.x)."""
    return re.sub(r"https?://(dx\.)?doi\.org/", "", doi.strip())


def is_valid_pdf(filepath: Path) -> bool:
    """
    Verifica se um arquivo é um PDF legítimo.

    [v4] Melhorias em relação à v5.3:
      - Detecta HTML disfarçado (<!DOCTYPE, <html, <body) que passa pelo
        magic number check quando o servidor retorna erro como HTML
      - Verifica presença do marcador %%EOF no final do arquivo
        (sinal de PDF completo, não truncado) para arquivos < 10 MB

    Validações em ordem:
      1. Tamanho mínimo de 1000 bytes
      2. Presença de %PDF no header (primeiros 20 bytes)
      3. [v4] Ausência de marcadores HTML no header
      4. [v7] Presença de %%EOF nos últimos 4 KB (qualquer tamanho)
    """
    try:
        size = filepath.stat().st_size
        if size < 1000:
            return False

        with open(filepath, "rb") as f:
            header = f.read(512)

        if b"%PDF" not in header[:20]:
            return False

        # [v4] Detectar HTML disfarçado (editoras retornam página de erro como PDF)
        html_markers = (b"<!DOCTYPE", b"<!doctype", b"<html", b"<HTML", b"<body", b"<BODY")
        if any(marker in header for marker in html_markers):
            return False

        # [v4] Verificar marcador %%EOF no final — truncados não o têm.
        # [v7] Sem exceções de tamanho: a v6 só checava arquivos < 10 MB e
        # ainda aceitava truncados entre 100 KB e 10 MB ("tolerância a EOF
        # mal-posicionado"), deixando PDFs corrompidos passarem — e o resume
        # os pulava para sempre. A janela de busca subiu de 1 KB para 4 KB,
        # que acomoda finais legítimos com lixo depois do %%EOF.
        with open(filepath, "rb") as f:
            f.seek(max(0, size - 4096))
            footer = f.read()
        if b"%EOF" not in footer:  # b"%%EOF" contém b"%EOF" — um check basta
            return False

        return True
    except Exception:
        return False


def _build_referer(url: str) -> dict[str, str]:
    """Constrói header Referer do mesmo domínio da URL de download."""
    parsed = urlparse(url)
    return {"Referer": f"{parsed.scheme}://{parsed.netloc}/"}


def download_file(
    url: str,
    filepath: Path,
    timeout: int = 45,
    _depth: int = 0,
    _retries: int = 0,
) -> tuple[bool, str]:
    """
    Baixa um arquivo de uma URL e valida se é um PDF legítimo.

    [v7] Melhorias em relação à v6:
      - Download ATÔMICO: escreve em <nome>.pdf.part e renomeia para .pdf
        só depois de validar. Execução interrompida não deixa mais um .pdf
        truncado que o resume pularia para sempre.
      - Retry também para status transitórios (429/500/502/503/504),
        honrando Retry-After quando presente — antes só Timeout retentava,
        e um 503 passageiro virava falha permanente da URL.
      - Streaming de verdade: o corpo é lido em blocos de 64 KB com teto
        incremental. A v6 pedia stream=True mas lia r.content, carregando
        o corpo INTEIRO na RAM antes de qualquer checagem — sem
        Content-Length, um arquivo de 500 MB passava batido pelo limite.
      - Resposta sempre fechada (finally) — os early-returns deixavam
        conexões de streaming abertas até o garbage collector passar.
      - Host desativado pelo circuit breaker → falha imediata com motivo
        explícito ("host bloqueado nesta execução"), sem tráfego.

    [v4] Melhorias em relação à v5.3:
      - Retry com backoff exponencial para timeouts transitórios.
        Máximo de 2 retentativas, com espera de 1s → 2s entre elas.
        Erros permanentes (403, 404, rede) não fazem retry.
      - _depth continua limitando recursão em HTML→PDF (max 1 nível)

    Fluxo de validação:
      1. GET com streaming, Referer dinâmico e redirects
      2. Verifica HTTP (403, 404, outros erros)
      3. Checa Content-Length contra MAX_PDF_SIZE (100 MB)
      4. Verifica magic number %PDF nos primeiros 20 bytes
      5. Se HTML, tenta extrair link de PDF da página (1 nível de recursão)
      6. Se content-type indica PDF ou octet-stream, salva e valida

    Args:
        url:      URL para download
        filepath: Caminho de destino para salvar o PDF
        timeout:  Tempo máximo de espera em segundos (default: 45)
        _depth:   [v5.2] Profundidade de recursão HTML→PDF (max 1)
        _retries: [v4]   Número de retentativas já feitas (max 2)

    Returns:
        Tupla (sucesso: bool, motivo: str)
    """
    _MAX_RETRIES = 2
    _BACKOFF_BASE = 1.0  # segundos
    # [v7] Status que merecem retry: transitórios por natureza.
    _TRANSIENT_STATUS = (429, 500, 502, 503, 504)

    # [v7] Download atômico: escreve aqui e renomeia só depois de validar.
    tmp_path = filepath.with_suffix(filepath.suffix + ".part")

    r = None
    try:
        headers = _build_referer(url)
        r = polite_get(
            url, timeout=timeout, stream=True, allow_redirects=True, headers=headers,
        )

        # [v7] Erro transitório → backoff (ou Retry-After) e nova tentativa
        if r.status_code in _TRANSIENT_STATUS:
            if _retries < _MAX_RETRIES:
                wait = _parse_retry_after(r.headers.get("Retry-After"))
                pause = wait if wait is not None else _BACKOFF_BASE * (2 ** _retries)
                time.sleep(min(pause, 30.0))
                return download_file(url, filepath, timeout, _depth, _retries + 1)
            return False, f"HTTP {r.status_code} ({_MAX_RETRIES + 1} tentativas)"

        if r.status_code == 403:
            return False, "HTTP 403"
        if r.status_code == 404:
            return False, "HTTP 404"
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"

        content_length = r.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_PDF_SIZE:
            return False, f"arquivo muito grande ({int(content_length) // (1024*1024)} MB)"

        content_type = r.headers.get("Content-Type", "").lower()

        # [v7] Leitura em streaming com teto incremental (ver docstring).
        chunks: list[bytes] = []
        received = 0
        for chunk in r.iter_content(chunk_size=64 * 1024):
            received += len(chunk)
            if received > MAX_PDF_SIZE:
                return False, f"arquivo muito grande (> {MAX_PDF_SIZE // (1024*1024)} MB)"
            chunks.append(chunk)
        content = b"".join(chunks)

        # CASO 1: Conteúdo começa com %PDF → salvar em .part, validar, renomear
        if b"%PDF" in content[:20]:
            tmp_path.write_bytes(content)
            if is_valid_pdf(tmp_path):
                tmp_path.replace(filepath)  # [v7] só agora vira .pdf
                return True, "ok"
            tmp_path.unlink(missing_ok=True)
            return False, "PDF inválido ou corrompido"

        # CASO 2: HTML → tentar extrair link de PDF embutido na página
        if "text/html" in content_type:
            if _depth > 1:
                return False, "recursão máxima atingida"
            pdf_link = extract_pdf_from_html(content, r.url)
            if pdf_link:
                return download_file(pdf_link, filepath, timeout=30, _depth=_depth + 1)
            return False, "retornou HTML"

        # CASO 3: Content-type indica PDF ou stream binário → salvar e validar
        if "pdf" in content_type or "octet-stream" in content_type:
            tmp_path.write_bytes(content)
            if is_valid_pdf(tmp_path):
                tmp_path.replace(filepath)  # [v7]
                return True, "ok"
            tmp_path.unlink(missing_ok=True)
            return False, "não é PDF válido"

        return False, f"tipo inesperado: {content_type[:30]}"

    except HostBlockedError:
        # [v7] Circuit breaker aberto para este host — sem tráfego, sem retry.
        return False, "host bloqueado nesta execução"

    except requests.Timeout:
        # [v4] Retry com backoff exponencial para timeouts
        tmp_path.unlink(missing_ok=True)
        if _retries < _MAX_RETRIES:
            wait = _BACKOFF_BASE * (2 ** _retries)
            time.sleep(wait)
            return download_file(url, filepath, timeout, _depth, _retries + 1)
        return False, f"timeout ({_MAX_RETRIES + 1} tentativas)"

    except requests.RequestException as e:
        tmp_path.unlink(missing_ok=True)
        return False, f"rede: {type(e).__name__}"

    finally:
        # [v7] Fechar a resposta sempre — cobre todos os early-returns.
        if r is not None:
            r.close()


def _resolve_url(href: str, page_url: str) -> str:
    """Resolve URL relativa para absoluta usando a URL da página.

    [v7] Reescrita sobre urllib.parse.urljoin: a versão manual não seguia a
    RFC 3986 — href começando com "?" perdia o último segmento do caminho
    (".../artigo?format=pdf" virava ".../?format=pdf") e "../" não era
    normalizado. urljoin cobre //, /, ?, #, ../ e URLs absolutas de graça.
    """
    return urljoin(page_url, href)


def _extract_pdf_bs4(content: bytes, page_url: str) -> str | None:
    """
    Extrai URL de PDF usando BeautifulSoup (mais robusto que regex).

    [v4] Usado como primeira tentativa quando beautifulsoup4 está instalado.
    Mais confiável para HTML malformado, atributos fora de ordem, etc.
    """
    try:
        soup = BeautifulSoup(content, "html.parser")

        # Meta tag citation_pdf_url (Highwire Press: BMJ, PNAS, Nature)
        meta = soup.find("meta", {"name": "citation_pdf_url"})
        if meta and meta.get("content"):
            return _resolve_url(meta["content"], page_url)

        # Link com type=application/pdf
        for link in soup.find_all("a", {"type": "application/pdf"}):
            href = link.get("href", "")
            if href:
                return _resolve_url(href, page_url)

        # Atributo data-download-url (BMJ, alguns journals)
        for elem in soup.find_all(attrs={"data-download-url": True}):
            url = elem["data-download-url"]
            if ".pdf" in url.lower():
                return _resolve_url(url, page_url)

        # Links <a> com /pdf/ no href (SAGE, T&F, Wiley, RSC)
        # [v7] Restrito ao MESMO host da página: este e o próximo são
        # padrões genéricos — o primeiro <a> apontando para outro domínio
        # podia ser um "artigo relacionado" ou anúncio, baixado e salvo com
        # o nome do artigo pedido (corrupção silenciosa da biblioteca).
        # Os padrões específicos acima (meta citation_pdf_url etc.) são
        # metadados declarados pela página e podem apontar para CDN externo.
        page_host = _host_of(page_url)
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/pdf/" in href and len(href) > 10:
                resolved = _resolve_url(href, page_url)
                if _host_of(resolved) == page_host:  # [v7]
                    return resolved

        # Links <a> terminando em .pdf — [v7] mesma restrição de host
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.lower().endswith(".pdf"):
                resolved = _resolve_url(href, page_url)
                if _host_of(resolved) == page_host:  # [v7]
                    return resolved

        # Embeds e iframes com PDF
        for tag in soup.find_all(["embed", "iframe"], src=True):
            src = tag["src"]
            if ".pdf" in src.lower():
                return _resolve_url(src, page_url)

    except Exception:
        pass

    return None


def extract_pdf_from_html(content: bytes, page_url: str) -> str | None:
    """
    Extrai URL de PDF embutida em uma página HTML de artigo acadêmico.

    [v4] Melhorias em relação à v5.3:
      - Tenta BeautifulSoup primeiro (se instalado) para parsing robusto
      - Fallback para regex com 8 padrões adicionais:
          * JSON-LD (pdfUrl, contentUrl)
          * RSC (pubs.rsc.org)
          * ACS (pubs.acs.org)
          * Springer download button
          * PLOS alternativo
          * IEEE data-test="pdf-link"
          * Hindawi/Wiley dynamic
          * Open Graph og:url para PDFs

    Args:
        content:  Conteúdo HTML da página em bytes
        page_url: URL da página (para resolver URLs relativas)

    Returns:
        URL absoluta do PDF se encontrada, ou None
    """
    # [v4] Tentar BeautifulSoup primeiro se disponível
    if _BS4_AVAILABLE:
        result = _extract_pdf_bs4(content, page_url)
        if result:
            return result

    # Fallback: regex
    try:
        # [v7] Renomeado de "html" para "html_text": o módulo stdlib html
        # agora é importado (escaping do relatório) e o nome colidia.
        html_text = content.decode("utf-8", errors="ignore")
    except Exception:
        return None

    # [v7] Cada padrão agora é (regex, só_mesmo_host). Os dois padrões
    # genéricos de <a> (qualquer "/pdf/" e qualquer ".pdf") só aceitam links
    # do host da própria página — mesma proteção contra "primeiro link
    # errado" aplicada na versão BeautifulSoup acima. Padrões de metadados
    # e de editora específica continuam aceitando qualquer host.
    patterns = [
        # --- Padrões existentes na v5.3 ---
        (r'<meta\s+name="citation_pdf_url"\s+content="([^"]+)"', False),
        (r"<meta\s+name='citation_pdf_url'\s+content='([^']+)'", False),
        (r'<a[^>]+href="([^"]+)"[^>]+type="application/pdf"', False),
        (r'data-download-url="([^"]+\.pdf[^"]*)"', False),
        (r'<a[^>]+href="([^"]+/pdf/[^"]+)"', True),   # [v7] genérico
        (r'<a[^>]+href="([^"]+\.pdf)"', True),        # [v7] genérico
        (r'<embed[^>]+src="([^"]+\.pdf[^"]*)"', False),
        (r'<iframe[^>]+src="([^"]+\.pdf[^"]*)"', False),

        # --- [v4] Novos padrões ---

        # JSON-LD: pdfUrl (PLOS, BMC, alguns journals modernos)
        (r'"pdfUrl":\s*"([^"]+\.pdf[^"]*)"', False),
        # JSON-LD: contentUrl (schema.org ScholarlyArticle)
        (r'"contentUrl":\s*"([^"]+\.pdf[^"]*)"', False),
        # JSON-LD: url genérico terminando em .pdf
        (r'"url":\s*"([^"https][^"]+\.pdf)"', False),

        # RSC (Royal Society of Chemistry) — download button
        (r'<a[^>]+href="(/content/articlepdf/[^"]+)"', False),
        # ACS Publications — PDF download link
        (r'<a[^>]+href="(/doi/pdf/[^"]+)"[^>]*>', False),
        # Springer — data-gtm-label (download button rastreado)
        (r'<a[^>]+href="([^"]+\.pdf[^"]*)"[^>]*data-gtm-label="[^"]*[Pp][Dd][Ff][^"]*"', False),
        # IEEE — data-test PDF link
        (r'<a[^>]+data-test="pdf-link"[^>]+href="([^"]+)"', False),
        # Open Graph og:url para PDFs (alguns preprint servers)
        (r'<meta[^>]+property="og:url"[^>]+content="([^"]+\.pdf[^"]*)"', False),
        # Meta tag dc.identifier com PDF
        (r'<meta[^>]+name="dc\.identifier"[^>]+content="(https?://[^"]+\.pdf)"', False),
    ]

    page_host = _host_of(page_url)
    for pattern, same_host_only in patterns:
        match = re.search(pattern, html_text, re.IGNORECASE)
        if match:
            pdf_url = _resolve_url(match.group(1), page_url)
            if same_host_only and _host_of(pdf_url) != page_host:  # [v7]
                continue
            return pdf_url

    return None


# ============================================================================
# FUNÇÕES DE SIMILARIDADE DE TÍTULOS
# ============================================================================
# Idênticas à v5.3: validação fuzzy para evitar baixar artigos errados
# quando a busca por título retorna resultados imprecisos.


def _normalize_title(title: str) -> str:
    """Normaliza título para comparação: minúsculas, sem pontuação, sem chaves BibTeX."""
    t = title.lower().strip()
    t = t.replace("{", "").replace("}", "")
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _title_ratio(input_title: str, result_title: str) -> float:
    """[v8] Razão de similaridade fuzzy entre dois títulos (0.0–1.0).

    Extraída de _titles_match para a descoberta de DOI poder ESCOLHER o melhor
    candidato (precisa da razão, não só do booleano). Títulos curtos demais
    (< 10 chars normalizados) retornam 0.0 — não dá para casar com segurança.
    """
    norm_input = _normalize_title(input_title)
    norm_result = _normalize_title(result_title)
    if len(norm_input) < 10 or len(norm_result) < 10:
        return 0.0
    return SequenceMatcher(None, norm_input, norm_result).ratio()


def _titles_match(input_title: str, result_title: str, threshold: float = 0.75) -> bool:
    """
    Verifica se dois títulos são suficientemente similares.

    Usa SequenceMatcher (stdlib) com threshold configurável.
    Retorna False para títulos muito curtos (< 10 chars normalizados).
    """
    return _title_ratio(input_title, result_title) >= threshold


# ============================================================================
# [v8] DESCOBERTA DE DOI (Crossref)
# ============================================================================
# Entradas .bib sem DOI são a maior causa de artigos não encontrados: sem DOI,
# Unpaywall/OpenAlex/DOAJ e a resolução por editora não têm chave de busca. A
# etapa abaixo tenta DESCOBRIR o DOI no Crossref por título + sobrenome do 1º
# autor e injeta o DOI na entrada, devolvendo as 10 fontes ao jogo.
#
# Precisão em primeiro lugar: um DOI ERRADO é pior que nenhum (levaria a baixar
# e salvar o PDF de outro artigo com o nome deste). Por isso NÃO confiamos no
# `score` do Crossref — nos testes de 2026-07-24, mirrors 'posted-content' de
# 2025 do "Attention is all you need" vinham no topo do score. A aceitação é
# validada pelo nosso código: título fuzzy ≥ threshold, sobrenome do 1º autor
# presente e ano dentro de ±1 (cobre a defasagem comum entre ano impresso e ano
# online sem deixar entrar mirror de outro ano). Quando nada valida, retorna ""
# e a entrada segue como "sem DOI" — nunca inventamos um DOI.


def _name_tokens(s: str) -> list[str]:
    """[v8] Tokens alfabéticos (≥2 letras, minúsculos, sem acento) de um nome —
    base para comparar sobrenomes de forma tolerante a acentos e hífens."""
    s = unidecode(s) if unidecode else s
    return [t for t in re.sub(r"[^a-z]+", " ", s.lower()).split() if len(t) > 1]


def _surname_in_authors(entry_surname: str, crossref_authors: list) -> bool:
    """[v8] True se o sobrenome do 1º autor da entrada compartilhar QUALQUER
    token com o campo `family` de algum autor do resultado do Crossref. Tolera
    'García Márquez' vs 'Marquez', 'von Neumann' vs 'Neumann', hífens. É sinal
    corroborante — os filtros fortes são o título fuzzy e o ano."""
    etoks = set(_name_tokens(entry_surname))
    if not etoks:
        return False
    for a in crossref_authors:
        if etoks & set(_name_tokens(a.get("family", ""))):
            return True
    return False


def _crossref_item_year(item: dict) -> int | None:
    """[v8] Ano de publicação de um item do Crossref (issued.date-parts[0][0])."""
    dp = (item.get("issued") or {}).get("date-parts") or [[None]]
    if dp and dp[0] and dp[0][0] is not None:
        try:
            return int(dp[0][0])
        except (TypeError, ValueError):
            return None
    return None


def try_crossref_doi(entry: dict, email: str, threshold: float = 0.75) -> str:
    """
    [v8] Descobre o DOI de uma entrada .bib SEM DOI, via Crossref REST.

    GET https://api.crossref.org/works
        ?query.bibliographic=<título>&query.author=<sobrenome>&rows=5
        &select=DOI,title,author,issued,type&mailto=<email>

    Retorna o DOI (string limpa, sem prefixo de URL) SOMENTE quando um dos 5
    primeiros resultados passa na validação nossa; caso contrário "". A
    validação (ver comentário da seção) é o que garante precisão — o `score`
    do Crossref não é medida de confiança.

    Args:
        entry:     dict do BibTeX (usa title, author, year).
        email:     e-mail de contato (polite pool do Crossref).
        threshold: limiar fuzzy de título (mesmo --threshold das outras fontes).

    Returns:
        DOI validado (ex.: "10.1016/s0022-2836(05)80360-2") ou "".
    """
    title = (entry.get("title") or "").strip().replace("{", "").replace("}", "")
    # Título curto demais não casa com segurança (mesma regra de _title_ratio).
    if len(_normalize_title(title)) < 10:
        return ""
    surname = _first_author_surname(entry.get("author", ""))
    entry_year = _entry_year(entry)

    params = {
        "query.bibliographic": title,
        "rows": 5,
        "select": "DOI,title,author,issued,type",
        "mailto": email,
    }
    if surname:
        params["query.author"] = surname

    try:
        r = polite_get_API("https://api.crossref.org/works", params=params, timeout=15)
    except requests.RequestException:
        return ""
    if r.status_code != 200:
        return ""
    try:
        items = r.json().get("message", {}).get("items", [])
    except ValueError:
        return ""

    # Escolhe o melhor candidato VÁLIDO: maior título fuzzy; desempate por ano
    # exato. Só entram candidatos que passam em título + sobrenome + ano.
    best_doi = ""
    best_fuzzy = -1.0
    best_year_exact = False
    for it in items:
        ct = it.get("title") or [""]
        fuzzy = _title_ratio(title, ct[0] if ct else "")
        if fuzzy < threshold:
            continue
        if surname and not _surname_in_authors(surname, it.get("author", [])):
            continue
        cyear = _crossref_item_year(it)
        year_exact = entry_year is not None and cyear == entry_year
        if entry_year is not None:
            # Com ano na entrada: exigir |Δano| ≤ 1 (impresso vs online).
            if cyear is None or abs(cyear - entry_year) > 1:
                continue
        else:
            # Sem ano na entrada: sem esse filtro, exigir título quase idêntico.
            if fuzzy < max(threshold, 0.90):
                continue
        doi = it.get("DOI") or ""
        if not doi:
            continue
        if fuzzy > best_fuzzy or (fuzzy == best_fuzzy and year_exact and not best_year_exact):
            best_doi = clean_doi(doi)
            best_fuzzy = fuzzy
            best_year_exact = year_exact
    return best_doi


# ============================================================================
# FONTES DE DOWNLOAD
# ============================================================================
# Cada função try_*() consulta uma fonte e retorna lista de URLs candidatas.
# O orquestrador (find_and_download) chama cada fonte em ordem e tenta
# baixar cada URL até obter sucesso.


def try_unpaywall(doi: str, email: str) -> list[str]:
    """
    Fonte 1: Unpaywall — base global de acesso aberto (~30M artigos).

    API: https://api.unpaywall.org/v2/{doi}?email={email}
    Retorna best_oa_location + lista de oa_locations.

    Deduplicação por URL (v5.2+) para evitar duplicatas com metadados
    diferentes para a mesma URL.
    """
    if not doi:
        return []
    urls = []
    try:
        r = polite_get_API(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": email},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            all_locations: list[dict] = []
            seen_loc_urls: set[str] = set()
            best = data.get("best_oa_location")
            if best:
                all_locations.append(best)
                for key in ("url_for_pdf", "url"):
                    if best.get(key):
                        seen_loc_urls.add(best[key])
            for loc in data.get("oa_locations", []):
                loc_id = loc.get("url_for_pdf") or loc.get("url")
                if loc_id and loc_id not in seen_loc_urls:
                    all_locations.append(loc)
                    for key in ("url_for_pdf", "url"):
                        if loc.get(key):
                            seen_loc_urls.add(loc[key])
            for loc in all_locations:
                pdf_url = loc.get("url_for_pdf")
                if pdf_url:
                    urls.append(pdf_url)
                page_url = loc.get("url")
                if page_url and page_url not in urls:
                    urls.append(page_url)
    except requests.RequestException:
        pass
    return urls


def try_semantic_scholar(entry: dict, doi: str, title_threshold: float = 0.75) -> list[str]:
    """
    Fonte 2: Semantic Scholar — Allen Institute for AI (~200M artigos).

    Estratégia dupla:
      1. Busca exata por DOI
      2. Busca por título com validação fuzzy (v5.3+)

    API: https://api.semanticscholar.org/graph/v1/paper/
    """
    urls: list[str] = []
    api_base = "https://api.semanticscholar.org/graph/v1/paper"

    if doi:
        try:
            r = polite_get_API(
                f"{api_base}/DOI:{doi}",
                params={"fields": "openAccessPdf,externalIds"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                oa_pdf = data.get("openAccessPdf")
                if oa_pdf and oa_pdf.get("url"):
                    urls.append(oa_pdf["url"])
        except requests.RequestException:
            pass

    if not urls:
        title = entry.get("title", "").strip().replace("{", "").replace("}", "")
        if title and len(title) > 15:
            try:
                r = polite_get_API(
                    f"{api_base}/search",
                    params={"query": title, "limit": 3, "fields": "openAccessPdf,title"},
                    timeout=10,
                )
                if r.status_code == 200:
                    for paper in r.json().get("data", []):
                        result_title = paper.get("title", "")
                        if not _titles_match(title, result_title, title_threshold):
                            continue
                        oa_pdf = paper.get("openAccessPdf")
                        if oa_pdf and oa_pdf.get("url"):
                            urls.append(oa_pdf["url"])
            except requests.RequestException:
                pass

    return urls


def try_openalex(entry: dict, doi: str, email: str, title_threshold: float = 0.75,
                 api_key: str = "") -> list[str]:
    """
    Fonte 3: OpenAlex — base aberta de metadados acadêmicos (~250M artigos).

    Estratégia dupla: busca por DOI (exata) e por título (fallback fuzzy).
    O parâmetro mailto ativa o "polite pool" com rate limit maior.

    [v7] api_key: desde 13/02/2026 a OpenAlex exige uma key (gratuita) para
    quase toda chamada; sem ela, ~100 req/dia. Quando presente, vai como
    parâmetro de query `api_key` — é o método documentado pela OpenAlex e o
    que funciona de forma estável (o header Authorization: Bearer é aceito
    de forma inconsistente). É HTTPS e o script loga só o host, nunca a URL
    completa, então a key não vaza em log.

    API: https://api.openalex.org/works/
    """
    urls: list[str] = []
    api_base = "https://api.openalex.org/works"

    # [v7] Parâmetros comuns às duas chamadas: mailto sempre; api_key quando
    # o usuário forneceu uma.
    base_params = {"mailto": email}
    if api_key:
        base_params["api_key"] = api_key

    if doi:
        try:
            r = polite_get_API(
                f"{api_base}/doi:{doi}",
                params=dict(base_params),
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                oa_url = data.get("open_access", {}).get("oa_url")
                if oa_url:
                    urls.append(oa_url)
                for loc in data.get("locations", []):
                    pdf_url = loc.get("pdf_url")
                    if pdf_url and pdf_url not in urls:
                        urls.append(pdf_url)
        except requests.RequestException:
            pass

    if not urls:
        title = entry.get("title", "").strip().replace("{", "").replace("}", "")
        if title and len(title) > 15:
            try:
                r = polite_get_API(
                    api_base,
                    params={**base_params, "search": title, "per_page": 3},
                    timeout=10,
                )
                if r.status_code == 200:
                    for work in r.json().get("results", []):
                        result_title = work.get("title", "")
                        if not _titles_match(title, result_title, title_threshold):
                            continue
                        oa_url = work.get("open_access", {}).get("oa_url")
                        if oa_url:
                            urls.append(oa_url)
            except requests.RequestException:
                pass

    return urls


def try_europe_pmc(entry: dict, doi: str, title_threshold: float = 0.75) -> list[str]:
    """
    Fonte 4 [v4]: Europe PMC — REST API direta do Europe PubMed Central.

    Diferença em relação à fonte PMC (Fonte 5):
      - Usa a REST API do EBI (www.ebi.ac.uk/europepmc) em vez do NCBI
      - Retorna diretamente URLs de fulltext sem converter para PMCID primeiro
      - Mais rápida e com melhor cobertura para artigos europeus e biomédicos

    Estratégia dupla:
      1. Busca por DOI via REST API
      2. Busca por título como fallback

    API: https://www.ebi.ac.uk/europepmc/webservices/rest/search
    Campos usados: pmcid, fullTextUrlList, isOpenAccess

    Args:
        entry: Dict com campos BibTeX (título para fallback)
        doi:   Identificador DOI do artigo

    Returns:
        Lista de URLs de PDF (Europe PMC)
    """
    urls: list[str] = []
    api_base = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def _parse_epmc_result(result: dict) -> list[str]:
        """Extrai URLs de PDF de um resultado Europe PMC."""
        found: list[str] = []
        pmcid = result.get("pmcid")
        if pmcid:
            # URL direta de PDF do Europe PMC (geralmente funciona bem)
            found.append(
                f"https://europepmc.org/backend/ptpmcrender.fcgi"
                f"?accid={pmcid}&blobtype=pdf"
            )
        # URLs de texto completo na resposta da API
        for ft_url in result.get("fullTextUrlList", {}).get("fullTextUrl", []):
            style = ft_url.get("documentStyle", "")
            url = ft_url.get("url", "")
            if url and style in ("pdf", "pdf/zip") and url not in found:
                found.append(url)
        return found

    # Estratégia 1: Busca por DOI
    if doi:
        try:
            r = polite_get_API(
                api_base,
                params={
                    "query": f'DOI:"{doi}"',
                    "format": "json",
                    "resultType": "core",
                    "pageSize": 3,
                },
                timeout=12,
            )
            if r.status_code == 200:
                data = r.json()
                for result in data.get("resultList", {}).get("result", []):
                    # Só usar resultados com acesso aberto
                    if result.get("isOpenAccess") == "Y":
                        for url in _parse_epmc_result(result):
                            if url not in urls:
                                urls.append(url)
        except requests.RequestException:
            pass

    # Estratégia 2: Busca por título
    if not urls:
        title = entry.get("title", "").strip().replace("{", "").replace("}", "")
        if title and len(title) > 15:
            try:
                r = polite_get_API(
                    api_base,
                    params={
                        "query": f'TITLE:"{title}" HAS_PDF:Y',
                        "format": "json",
                        "resultType": "core",
                        "pageSize": 3,
                    },
                    timeout=12,
                )
                if r.status_code == 200:
                    for result in r.json().get("resultList", {}).get("result", []):
                        result_title = result.get("title", "")
                        # [v7] Antes chamava _titles_match sem o threshold —
                        # o --threshold do usuário era ignorado nesta fonte.
                        if not _titles_match(title, result_title, title_threshold):
                            continue
                        if result.get("isOpenAccess") == "Y":
                            for url in _parse_epmc_result(result):
                                if url not in urls:
                                    urls.append(url)
            except requests.RequestException:
                pass

    return urls


def try_pmc(entry: dict, doi: str, email: str) -> list[str]:
    """
    Fonte 5: PMC — PubMed Central via NCBI E-utilities (fallback).

    Converte DOI → PMCID via API de conversão, depois monta URLs
    de download. Mantida como fallback após try_europe_pmc (Fonte 4)
    para artigos que não aparecem na busca do Europe PMC mas têm PMCID.

    APIs:
      - https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/
      - https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi
    """
    urls = []
    pmcid = None

    if doi:
        try:
            r = polite_get_API(
                "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/",
                params={"ids": doi, "format": "json", "tool": "bibfix", "email": email},
                timeout=10,
            )
            if r.status_code == 200:
                records = r.json().get("records", [])
                if records:
                    pmcid = records[0].get("pmcid")
        except requests.RequestException:
            pass

    if not pmcid:
        title = entry.get("title", "").strip().replace("{", "").replace("}", "")
        if title and len(title) > 10:
            try:
                r = polite_get_API(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params={
                        "db": "pmc", "term": f'{title}[Title]',
                        "retmode": "json", "retmax": 1,
                        "tool": "bibfix", "email": email,
                    },
                    timeout=10,
                )
                if r.status_code == 200:
                    id_list = r.json().get("esearchresult", {}).get("idlist", [])
                    if id_list:
                        pmcid = f"PMC{id_list[0]}"
            except requests.RequestException:
                pass

    if pmcid:
        urls.append(f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf")
        urls.append(f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/")

    return urls


def try_arxiv(entry: dict, doi: str, title_threshold: float = 0.75) -> list[str]:
    """
    Fonte 6 [v4]: arXiv — repositório de preprints acadêmicos.

    arXiv (arxiv.org) hospeda ~2.5 milhões de preprints de acesso aberto
    em física, matemática, ciência da computação, biologia quantitativa,
    estatística, economia e finanças. Todos os artigos têm PDF gratuito.

    Estratégia:
      1. Se o DOI contém "arxiv" (ex: 10.48550/arXiv.xxxx.xxxxx), extrai
         o ID diretamente e monta a URL de PDF sem fazer request à API.
      2. Busca por título na API arXiv (XML Atom) com validação fuzzy.
         Usa a query field=ti: (title) para precisão.

    Como o arXiv serve preprints (versão anterior à publicação), o PDF
    pode ter diferenças menores em relação à versão publicada.

    API: https://export.arxiv.org/api/query
    Resposta: XML Atom com namespace http://www.w3.org/2005/Atom

    Args:
        entry:           Dict com campos BibTeX (título para busca)
        doi:             Identificador DOI (pode conter ID arXiv)
        title_threshold: Limiar de similaridade fuzzy (default: 0.75)

    Returns:
        Lista de URLs de PDF no arXiv
    """
    urls: list[str] = []

    # Estratégia 1: DOI que contém ID arXiv diretamente
    # Formatos: 10.48550/arXiv.2310.12345 ou arxiv:2310.12345
    if doi:
        arxiv_match = re.search(
            r'(?:arxiv[:/]|10\.48550/arxiv\.)(\d{4}\.\d{4,5}(?:v\d+)?)',
            doi, re.IGNORECASE,
        )
        if arxiv_match:
            arxiv_id = arxiv_match.group(1)
            return [f"https://arxiv.org/pdf/{arxiv_id}.pdf"]

    # Estratégia 2: Busca por título na API arXiv
    title = entry.get("title", "").strip().replace("{", "").replace("}", "")
    if not title or len(title) < 15:
        return urls

    try:
        r = polite_get_API(
            "https://export.arxiv.org/api/query",
            params={
                "search_query": f'ti:"{title}"',
                "max_results": 3,
                "sortBy": "relevance",
            },
            timeout=15,
        )
        if r.status_code != 200:
            return urls

        # Parsear resposta XML Atom
        root = ET.fromstring(r.content)
        atom_ns = "http://www.w3.org/2005/Atom"

        for entry_elem in root.findall(f"{{{atom_ns}}}entry"):
            # Verificar similaridade do título
            title_elem = entry_elem.find(f"{{{atom_ns}}}title")
            if title_elem is None:
                continue
            result_title = (title_elem.text or "").strip()
            if not _titles_match(title, result_title, title_threshold):
                continue

            # Encontrar link de PDF (arXiv sempre tem link com title="pdf")
            for link in entry_elem.findall(f"{{{atom_ns}}}link"):
                if link.get("title") == "pdf":
                    pdf_href = link.get("href", "")
                    if pdf_href:
                        # Normalizar: http→https, garantir extensão .pdf
                        pdf_href = pdf_href.replace("http://", "https://")
                        if "/abs/" in pdf_href:
                            pdf_href = pdf_href.replace("/abs/", "/pdf/")
                        if not pdf_href.endswith(".pdf"):
                            pdf_href += ".pdf"
                        if pdf_href not in urls:
                            urls.append(pdf_href)
                        break

    except (requests.RequestException, ET.ParseError):
        pass

    return urls


def try_doaj(doi: str) -> list[str]:
    """
    Fonte 8 [v4]: DOAJ — Directory of Open Access Journals.

    DOAJ (doaj.org) é o índice mais confiável de journals de acesso aberto,
    verificando qualidade editorial. Indexa 20.000+ revistas verificadas
    (não inclui journals predatórios) com 10M+ artigos.

    Só funciona para artigos publicados em journals indexados no DOAJ.
    Principalmente útil para journals de nicho não cobertos por Unpaywall.

    A API retorna links de fulltext (geralmente landing page, não PDF direto).
    O download_file tentará extrair o PDF via extract_pdf_from_html.

    API: https://doaj.org/api/v3/search/articles/
    Query: ?q=doi:"10.xxxx/yyy"&pageSize=1

    Args:
        doi: Identificador DOI do artigo

    Returns:
        Lista de URLs (fulltext ou PDF) do artigo no DOAJ
    """
    if not doi:
        return []
    urls: list[str] = []
    try:
        r = polite_get_API(
            "https://doaj.org/api/v3/search/articles/",
            params={"q": f'doi:"{doi}"', "pageSize": 3},
            timeout=12,
        )
        if r.status_code == 200:
            data = r.json()
            for result in data.get("results", []):
                bibjson = result.get("bibjson", {})
                for link in bibjson.get("link", []):
                    link_type = link.get("type", "")
                    url = link.get("url", "")
                    if url and link_type in ("fulltext", "pdf"):
                        if url not in urls:
                            urls.append(url)
    except requests.RequestException:
        pass
    return urls


def try_core(entry: dict, doi: str, title_threshold: float = 0.75) -> list[str]:
    """
    Fonte 7: CORE — maior agregador de repositórios institucionais.

    CORE (core.ac.uk) agrega 300M+ artigos de ~10.000 repositórios.
    Especialmente útil para encontrar versões em repositórios universitários
    (green open access).

    Estratégia dupla: busca por DOI (exata) e por título (fallback fuzzy).

    API: https://api.core.ac.uk/v3/search/works
    """
    urls: list[str] = []
    api_base = "https://api.core.ac.uk/v3"

    if doi:
        try:
            r = polite_get_API(
                f"{api_base}/search/works",
                params={"q": f'doi:"{doi}"', "limit": 3},
                timeout=12,
            )
            if r.status_code == 200:
                for result in r.json().get("results", []):
                    dl_url = result.get("downloadUrl")
                    if dl_url:
                        urls.append(dl_url)
                    for link in result.get("sourceFulltextUrls", []):
                        if link and link not in urls:
                            urls.append(link)
        except requests.RequestException:
            pass

    if not urls:
        title = entry.get("title", "").strip().replace("{", "").replace("}", "")
        if title and len(title) > 15:
            try:
                r = polite_get_API(
                    f"{api_base}/search/works",
                    params={"q": f'title:"{title}"', "limit": 3},
                    timeout=12,
                )
                if r.status_code == 200:
                    for result in r.json().get("results", []):
                        result_title = result.get("title", "")
                        if not _titles_match(title, result_title, title_threshold):
                            continue
                        dl_url = result.get("downloadUrl")
                        if dl_url:
                            urls.append(dl_url)
            except requests.RequestException:
                pass

    return urls


# Cache de resolução de DOI — compartilhado entre try_doi_redirect e try_scielo
# para evitar requests duplicados quando ambas consultam o mesmo DOI.

def _resolve_doi(doi: str, cache: dict[str, str] | None = None) -> str | None:
    """
    Resolve um DOI para sua URL final via doi.org, com cache opcional.

    Args:
        doi:   DOI a resolver
        cache: Dict {doi: url_final} compartilhado. Se None, sem cache.

    Returns:
        URL final após seguir todos os redirects, ou None se falhar.
    """
    if cache is not None and doi in cache:
        return cache[doi]
    try:
        r = polite_get(f"https://doi.org/{doi}", timeout=20, allow_redirects=True)
        final_url = r.url
        if cache is not None:
            cache[doi] = final_url
        return final_url
    except requests.RequestException:
        return None


def try_doi_redirect(doi: str, doi_cache: dict[str, str] | None = None) -> list[str]:
    """
    Fonte 9: DOI redirect + padrões de URL por editora.

    Resolve o DOI via doi.org e aplica padrões específicos de cada editora
    para construir URLs diretas para o PDF.

    [v4] Novos padrões adicionados:
      - RSC (Royal Society of Chemistry): /content/articlepdf/
      - ACS (American Chemical Society):  /doi/pdf/ ou /doi/epdf/
      - Karger (biomédico suíço):         /Article/Pdf/
      - LWW / Lippincott:                 /action/showPdf?pii=

    Editoras suportadas (28 padrões):
      ScienceDirect, SpringerLink, IEEE, ACM, BMJ, JAMA, Nature, Lancet,
      Wiley, SAGE, Taylor & Francis, PNAS, AJPH, Oxford Academic, Cambridge,
      Emerald, De Gruyter, SciELO, MDPI, Frontiers, PLOS, BMC, PeerJ,
      Hindawi, RSC [v4], ACS [v4], Karger [v4], LWW [v4]

    Args:
        doi:       Identificador DOI do artigo
        doi_cache: Cache compartilhado de resolução de DOI

    Returns:
        Lista de URLs candidatas para download de PDF
    """
    if not doi:
        return []
    urls: list[str] = []

    try:
        final_url = _resolve_doi(doi, doi_cache)
        if not final_url:
            return []

        if final_url.lower().endswith(".pdf"):
            urls.append(final_url)

        # --- Padrões existentes (v5.3) ---

        if "bmj.com" in final_url:
            base = final_url.split("?")[0].rstrip("/")
            urls.append(base + ".full.pdf")
            urls.append(base + ".full.pdf+html")

        if "jamanetwork.com" in final_url:
            urls.append(final_url.replace("/fullarticle/", "/articlepdf/"))
            match = re.search(r"/fullarticle/(\d+)", final_url)
            if match:
                aid = match.group(1)
                urls.append(f"https://jamanetwork.com/journals/jama/articlepdf/{aid}")

        if "nature.com" in final_url:
            base = final_url.split("?")[0].rstrip("/")
            urls.append(base + ".pdf")

        if "thelancet.com" in final_url:
            pii_match = re.search(r"/article/([^/]+)/", final_url)
            if pii_match:
                pii = pii_match.group(1)
                urls.append(f"https://www.thelancet.com/action/showPdf?pii={pii}")

        if "wiley.com" in final_url:
            urls.append(re.sub(r"/doi/(abs|full)/", "/doi/pdfdirect/", final_url))
            urls.append(re.sub(r"/doi/(abs|full)/", "/doi/pdf/", final_url))

        if "sagepub.com" in final_url:
            urls.append(re.sub(r"/doi/(abs|full)/", "/doi/pdf/", final_url))

        if "tandfonline.com" in final_url:
            urls.append(re.sub(r"/doi/(abs|full)/", "/doi/pdf/", final_url))
            urls.append(final_url.replace("/full/", "/pdf/"))

        if "pnas.org" in final_url:
            base = final_url.split("?")[0].rstrip("/")
            urls.append(base + ".full.pdf")

        if "ajph" in final_url.lower() or "apha.org" in final_url:
            urls.append(re.sub(r"/doi/(abs|full)/", "/doi/pdf/", final_url))

        if "academic.oup.com" in final_url:
            urls.append(final_url.replace("/article/", "/article-pdf/"))
            urls.append(final_url + "?redirectedFrom=PDF")

        if "scielo" in final_url:
            if "/abstract/" in final_url:
                urls.append(final_url.replace("/abstract/", "/pdf/"))

        if "mdpi.com" in final_url:
            urls.append(final_url.replace("/htm", "/pdf"))

        if "frontiersin.org" in final_url and "/full" in final_url:
            urls.append(final_url.replace("/full", "/pdf"))

        if "plos" in final_url.lower() and "article" in final_url:
            urls.append(
                final_url.replace("article?id=", "article/file?id=") + "&type=printable"
            )

        if "biomedcentral.com" in final_url or "springeropen.com" in final_url:
            if "/articles/" in final_url:
                urls.append(final_url.replace("/articles/", "/track/pdf/") + ".pdf")
                urls.append(final_url.replace("/articles/", "/counter/pdf/") + ".pdf")

        if "peerj.com" in final_url:
            urls.append(final_url.rstrip("/") + ".pdf")

        if "hindawi.com" in final_url:
            urls.append(final_url.rstrip("/") + "/pdf")

        if "sciencedirect.com" in final_url or "linkinghub.elsevier.com" in final_url:
            pii_match = re.search(r"/pii/([A-Z0-9]+)", final_url)
            if pii_match:
                pii = pii_match.group(1)
                urls.append(
                    f"https://www.sciencedirect.com/science/article/pii/{pii}/pdfft"
                    "?isDTMRedir=true&download=true"
                )
                urls.append(
                    f"https://www.sciencedirect.com/science/article/pii/{pii}/pdf"
                )
                urls.append(
                    f"https://www.sciencedirect.com/science/article/pii/{pii}"
                )

        if "link.springer.com" in final_url:
            doi_match = re.search(r"/article/(10\.\d{4,}/[^\s?#]+)", final_url)
            if doi_match:
                article_doi = doi_match.group(1)
                urls.append(f"https://link.springer.com/content/pdf/{article_doi}.pdf")
            if doi:
                urls.append(f"https://link.springer.com/openurl/pdf?id=doi:{doi}")

        if "ieeexplore.ieee.org" in final_url:
            doc_match = re.search(r"/document/(\d+)", final_url)
            if doc_match:
                doc_id = doc_match.group(1)
                urls.append(
                    f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber={doc_id}"
                )
                urls.append(
                    f"https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber={doc_id}"
                )

        if "dl.acm.org" in final_url:
            urls.append(re.sub(r"/doi/(abs/)?", "/doi/pdf/", final_url))

        if "cambridge.org" in final_url:
            base = final_url.split("?")[0].rstrip("/")
            urls.append(base + "/pdf")
            urls.append(final_url.replace("/article/", "/article/pdf/"))

        if "emerald.com" in final_url:
            base = final_url.split("?")[0].rstrip("/")
            urls.append(base + "/full/pdf")

        if "degruyter.com" in final_url:
            base = final_url.split("?")[0].rstrip("/")
            urls.append(base + "/pdf")
            urls.append(base.replace("/html", "/pdf"))

        # --- [v4] Novos padrões de editoras ---

        # RSC (Royal Society of Chemistry) — química
        # Padrão: /en/content/article/... → /en/content/articlepdf/...
        if "pubs.rsc.org" in final_url:
            urls.append(final_url.replace("/content/article/", "/content/articlepdf/"))
            # Alternativa: adicionar /pdf no final
            base = final_url.split("?")[0].rstrip("/")
            if not base.endswith("/pdf"):
                urls.append(base + "/pdf")

        # ACS (American Chemical Society) — química e materiais
        # Padrão: /doi/abs/... ou /doi/full/... → /doi/pdf/... ou /doi/epdf/...
        if "pubs.acs.org" in final_url:
            urls.append(re.sub(r"/doi/(abs|full)/", "/doi/pdf/", final_url))
            urls.append(re.sub(r"/doi/(abs|full)/", "/doi/epdf/", final_url))

        # Karger Publishers (biomédico, especialidades médicas)
        # Padrão: /Article/FullText/{id} → /Article/Pdf/{id}
        if "karger.com" in final_url:
            urls.append(re.sub(r"/Article/(FullText|Abstract)/", "/Article/Pdf/", final_url))
            base = final_url.split("?")[0].rstrip("/")
            # Tentar adicionar /pdf diretamente
            if "/Article/" in base:
                urls.append(base + "/pdf")

        # LWW / Wolters Kluwer (medicina clínica, enfermagem)
        # Padrão: /doi/fulltext/... → /doi/pdf/... ou showPdf
        if "journals.lww.com" in final_url:
            urls.append(re.sub(r"/doi/(fulltext|abstract)/", "/doi/pdf/", final_url))
            # Formato showPdf com PII
            pii_match = re.search(r"/pii/([^/?#]+)", final_url)
            if pii_match:
                pii = pii_match.group(1)
                urls.append(f"https://journals.lww.com/action/showPdf?pii={pii}")

        # Editora não reconhecida → tenta a landing page (extract_pdf_from_html)
        if not urls:
            urls.append(final_url)

    except requests.RequestException:
        pass

    return urls


def try_scielo(entry: dict, doi: str, doi_cache: dict[str, str] | None = None,
               title_threshold: float = 0.75) -> list[str]:
    """
    Fonte 10: SciELO — periódicos latino-americanos (~900k artigos).

    [v4] Reescrita completa. Melhorias em relação à v5.3:

    1. Ativação ampliada: antes só ativava quando o DOI continha "scielo"
       (falso negativo frequente). Agora ativa para:
         - DOIs com prefixo 10.1590/ (SciELO Brasil) e outros prefixos comuns
         - Qualquer DOI que resolva para um domínio SciELO
         - Busca por título como último recurso (sem DOI)

    2. Padrões de URL completos:
         - Formato novo:    /j/{abbrev}/a/{id}/  → ?format=pdf
         - Formato legado:  /abstract/           → /pdf/
         - Formato PHP:     sci_arttext          → sci_pdf

    3. Cobre múltiplos domínios:
         scielo.br, scielo.org, scielo.cl, scielo.org.mx, scielo.org.co, etc.

    4. Fallback via SciELO Search API por título (artigos sem DOI ou quando
       a resolução do DOI não retorna URL SciELO reconhecida).

    Args:
        entry:     Dict com campos BibTeX (título para busca por fallback)
        doi:       Identificador DOI do artigo
        doi_cache: Cache compartilhado de resolução de DOI

    Returns:
        Lista de URLs candidatas de PDF no SciELO
    """
    urls: list[str] = []

    # Prefixos DOI que pertencem à plataforma SciELO
    # 10.1590 = SciELO Brasil (principal)
    # 10.4025, 10.17058 = outros publishers brasileiros indexados no SciELO
    SCIELO_DOI_PREFIXES = ("10.1590/", "10.4025/", "10.17058/", "10.1612/")

    # Domínios SciELO por país
    SCIELO_DOMAINS = (
        "scielo.br", "scielo.org", "scielo.cl", "scielo.org.mx",
        "scielo.org.co", "scielo.org.ar", "scielo.conicyt.cl",
        "scielo.sld.cu", "scielo.org.pe", "scielo.edu.uy",
    )

    def _is_scielo_url(url: str) -> bool:
        return any(d in url for d in SCIELO_DOMAINS)

    def _extract_pdf_urls(resolved_url: str) -> list[str]:
        """Gera URLs de PDF a partir de uma URL SciELO resolvida."""
        found: list[str] = []

        # Padrão 1 (novo): /j/{abbrev}/a/{id}/ → ?format=pdf
        # Ex: https://www.scielo.br/j/rsp/a/3fMGhXmGkknLCy7bNRFvDSd/
        if "/j/" in resolved_url and "/a/" in resolved_url:
            base = resolved_url.split("?")[0].rstrip("/")
            found.append(base + "/?format=pdf")
            # Formato alternativo sem barra final
            found.append(base + "?format=pdf")

        # Padrão 2 (legado): /abstract/ → /pdf/
        # Ex: https://www.scielo.br/abstract/rsp/v53/0034-8910...
        if "/abstract/" in resolved_url:
            found.append(resolved_url.replace("/abstract/", "/pdf/"))

        # Padrão 3 (PHP legado): scielo.php?script=sci_arttext → sci_pdf
        # Ex: https://www.scielo.br/scielo.php?script=sci_arttext&pid=S0034...
        if "scielo.php" in resolved_url and "sci_arttext" in resolved_url:
            found.append(resolved_url.replace("sci_arttext", "sci_pdf"))
            # Tentar também o formato novo via PID
            pid_match = re.search(r"pid=([^&\s]+)", resolved_url)
            if pid_match:
                pid = pid_match.group(1)
                # Extrair domínio base para construir URL alternativa
                for domain in SCIELO_DOMAINS:
                    if domain in resolved_url:
                        found.append(
                            f"https://www.{domain}/scielo.php"
                            f"?script=sci_pdf&pid={pid}&tlng=pt"
                        )
                        break

        return found

    # ---- Estratégia 1: via DOI ----
    if doi:
        is_scielo_prefix = any(doi.startswith(p) for p in SCIELO_DOI_PREFIXES)
        is_scielo_text = "scielo" in doi.lower()

        # [v7] Só resolve o DOI quando ele já aparenta ser SciELO. A v6
        # resolvia TODO DOI "para confirmar" — ou seja, cada artigo que
        # chegava até esta fonte gerava um acesso ao doi.org que terminava
        # na landing page da editora, mesmo com --doi-scrape desligado.
        # Era essa, aliás, a rota que envenenava o circuit breaker com um
        # 403 de editora atribuído ao doi.org. O custo é perder o caso raro
        # de DOI não-SciELO que redireciona para o SciELO; a busca por
        # título (estratégia 2, abaixo) cobre esse resto.
        resolved_url = None
        if is_scielo_prefix or is_scielo_text:
            resolved_url = _resolve_doi(doi, doi_cache)

        if resolved_url and _is_scielo_url(resolved_url):
            for url in _extract_pdf_urls(resolved_url):
                if url not in urls:
                    urls.append(url)
        elif is_scielo_prefix or is_scielo_text:
            # DOI parece ser SciELO mas não resolveu para URL reconhecida
            # Tentar construir URL diretamente a partir do DOI
            # Ex: 10.1590/S0034-89102019000100001 → PID = S0034-89102019000100001
            pid_from_doi = re.search(r"10\.\d{4,}/(.+)$", doi)
            if pid_from_doi:
                pid = pid_from_doi.group(1).strip("/")
                urls.append(
                    f"https://www.scielo.br/scielo.php"
                    f"?script=sci_pdf&pid={pid}&tlng=pt"
                )
                urls.append(
                    f"https://www.scielo.br/scielo.php"
                    f"?script=sci_pdf&pid={pid}&tlng=en"
                )

    # ---- Estratégia 2: SciELO Search API por título ----
    # Ativada se: nenhuma URL encontrada até agora OU não há DOI
    if not urls:
        title = entry.get("title", "").strip().replace("{", "").replace("}", "")
        if title and len(title) > 15:
            try:
                # SciELO Search usa Elasticsearch com endpoint público
                r = polite_get_API(
                    "https://search.scielo.org/",
                    params={
                        "q": f'ti:"{title}"',
                        "lang": "pt,en,es",
                        "count": 3,
                        "output": "ris",
                        "format": "json",
                    },
                    timeout=12,
                )
                if r.status_code == 200:
                    data = r.json()
                    hits = data.get("hits", {}).get("hits", [])
                    for hit in hits[:3]:
                        src = hit.get("_source", {})
                        result_title = src.get("ti", [None])[0] if src.get("ti") else ""
                        # Validação fuzzy básica
                        # [v7] threshold do usuário agora vale aqui também
                        if result_title and not _titles_match(title, result_title,
                                                              title_threshold):
                            continue
                        # Extrair URL do PDF ou do artigo
                        pdf_urls = src.get("pdf_url", [])
                        if isinstance(pdf_urls, list):
                            for u in pdf_urls:
                                if u and u not in urls:
                                    urls.append(u)
                        # Fallback: URL do artigo (extract_pdf_from_html vai achar o PDF)
                        ur = src.get("ur", [])
                        if isinstance(ur, list) and ur:
                            page_url = ur[0]
                            if page_url and page_url not in urls:
                                urls.append(page_url)
            except requests.RequestException:
                pass

    return urls


# ============================================================================
# ORQUESTRADOR
# ============================================================================


def find_and_download(
    entry: dict, filepath: Path, config: Config
) -> tuple[bool, str, str, str]:
    """
    Tenta baixar o PDF de um artigo usando todas as 10 fontes disponíveis.

    Percorre as fontes em ordem de confiabilidade/cobertura:
      1. Unpaywall       — API rápida, links mais confiáveis
      2. Semantic Scholar — boa cobertura, busca por título
      3. OpenAlex        — cobertura ampla, dados abertos
      4. Europe PMC      — REST API direta, melhor para biomédicos
      5. PMC             — NCBI E-utilities (fallback do Europe PMC)
      6. arXiv           — preprints CS/física/matemática/biologia
      7. CORE            — repositórios institucionais
      8. DOAJ            — journals open access verificados
      9. DOI-PDF         — fallback com 28 padrões de editora
      10. SciELO         — específico para América Latina

    URLs já testadas são ignoradas (deduplicação via set).
    O espaçamento entre requisições fica todo a cargo de polite_get (por
    host); dentro de cada fonte, as URLs candidatas são tentadas em ordem
    de risco do host — repositórios OA antes de editoras ([v7]).

    Args:
        entry:    Dict com campos do BibTeX
        filepath: Caminho de destino para salvar o PDF
        config:   Objeto Config com email e thresholds

    Returns:
        Tupla (sucesso, nome_fonte, motivo, url_final):
          - (True,  "Unpaywall", "ok",       "https://...")
          - (False, "PMC",       "HTTP 403…", "https://doi.org/...")
          - (False, "",          "nenhuma URL encontrada", "")
        url_final é a URL resolvida pelo DOI redirect (útil para diagnóstico).
    """
    doi = clean_doi(entry.get("doi", "")) if entry.get("doi") else ""
    email = config.email
    threshold = config.title_match_threshold
    openalex_key = config.openalex_api_key  # [v7]

    # Cache compartilhado entre DOI-PDF e SciELO para evitar request duplo.
    # Após a execução, doi_cache[doi] == URL final resolvida pelo doi.org.
    doi_cache: dict[str, str] = {}

    sources = [
        ("Unpaywall",   lambda: try_unpaywall(doi, email)),
        ("SemScholar",  lambda: try_semantic_scholar(entry, doi, threshold)),
        ("OpenAlex",    lambda: try_openalex(entry, doi, email, threshold, openalex_key)),  # [v7] key
        ("EuropePMC",   lambda: try_europe_pmc(entry, doi, threshold)),  # [v7] threshold
        ("PMC",         lambda: try_pmc(entry, doi, email)),
        ("arXiv",       lambda: try_arxiv(entry, doi, threshold)),
        ("CORE",        lambda: try_core(entry, doi, threshold)),
        ("DOAJ",        lambda: try_doaj(doi)),
    ]

    # [v6] DOI-PDF fica atrás de flag: é a fonte que bate direto em editora.
    if config.enable_doi_scrape:
        sources.append(("DOI-PDF", lambda: try_doi_redirect(doi, doi_cache)))

    sources.append(("SciELO", lambda: try_scielo(entry, doi, doi_cache, threshold)))

    all_attempts: list[tuple[str, str]] = []
    seen_urls: set[str] = set()

    for source_name, finder in sources:
        try:
            # [v7] Ordenar por risco do host: APIs e repositórios OA antes
            # de editoras. O Unpaywall costuma listar a URL da editora
            # primeiro; tentar o repositório antes evita 403 desnecessário
            # (e strike no circuit breaker) quando existe cópia OA tranquila.
            # sorted() é estável: preserva a ordem da fonte dentro de cada
            # categoria de risco.
            candidate_urls = sorted(finder(), key=_host_rank)
            for url in candidate_urls:
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                success, reason = download_file(url, filepath)
                if success:
                    return True, source_name, "ok", doi_cache.get(doi, "")
                all_attempts.append((source_name, reason))
                # [v6] Sem sleep fixo aqui: polite_get já garante o intervalo
                # mínimo por host, que é o que realmente importa.
        except Exception as e:
            all_attempts.append((source_name, str(e)[:40]))

    final_url = doi_cache.get(doi, "")
    if all_attempts:
        reasons = "; ".join(f"{s}:{r}" for s, r in all_attempts[:5])
        return False, all_attempts[0][0], reasons, final_url
    return False, "", "nenhuma URL encontrada", final_url



# ============================================================================
# DIAGNÓSTICO E RELATÓRIO HTML  [v5]
# ============================================================================

# Domínios conhecidos por retornar 403 via proteção anti-bot, mas cujo
# conteúdo É de acesso aberto e pode ser baixado manualmente no navegador.
_BOT_PROTECTED_OA_DOMAINS = (
    "mdpi.com",
    "frontiersin.org",
    "hindawi.com",
    "springeropen.com",
    "biomedcentral.com",
    "plos.org",
    "plosone.org",
    "f1000research.com",
    "elifesciences.org",
)

# Palavras-chave no corpo da resposta que indicam bloqueio anti-bot
_BOT_BODY_MARKERS = (
    b"Access Denied",
    b"access denied",
    b"Akamai",
    b"akamai",
    b"Cloudflare",
    b"cloudflare",
    b"DDOS-GUARD",
    b"ddos-guard",
    b"Please enable JavaScript",
    b"Pardon Our Interruption",
)


def classify_failure(doi: str, final_url: str, reason: str,
                     probe: bool = True) -> dict:
    """
    [v5] Classifica o motivo de falha de um artigo não baixado.

    Faz uma requisição HTTP leve (GET parcial) para a URL resolvida
    e determina o tipo de falha:

      "bot_protect"  — servidor retorna 403 + corpo com marcadores Akamai/
                       Cloudflare, OU domínio é sabidamente OA mas bloqueia
                       robôs. O artigo É acessível manualmente no navegador.
      "paywall"      — artigo existe mas está atrás de paywall real (403/401
                       sem marcadores bot, ou Elsevier/Wiley ScienceDirect).
      "html_ok"      — servidor retorna 200 HTML (landing page acessível),
                       mas o script não conseguiu extrair o PDF.
      "blocked_run"  — [v7] o host foi desativado pelo circuit breaker
                       durante ESTA execução. Não é paywall nem erro: é
                       "rode de novo mais tarde". A v6 classificava isso
                       como "Erro de rede", apontando a direção errada.
      "server_error" — HTTP 5xx, timeout, ou URL expirada/inválida.
      "no_url"       — não havia URL para tentar (artigo sem DOI válido,
                       fontes sem cobertura).

    [v7] probe=False (--no-probe): classifica apenas pelo `reason` já
    registrado durante o download, sem gerar NENHUMA requisição extra —
    útil quando a execução já terminou com hosts sensíveis bloqueados.

    Args:
        doi:       DOI limpo do artigo (pode ser vazio string)
        final_url: URL resolvida pelo doi.org (pode ser vazio string)
        reason:    Motivo de falha retornado por find_and_download

    Returns:
        Dict com chaves:
          "type"    : str  — um dos valores acima
          "label"   : str  — rótulo legível em português
          "url"     : str  — URL recomendada para acesso manual
          "detail"  : str  — detalhe técnico adicional
    """
    if not final_url and not doi:
        return {
            "type": "no_url",
            "label": "Sem DOI / sem cobertura",
            "url": "",
            "detail": reason,
        }

    # URL para diagnóstico: preferir final_url (já resolvida), senão doi.org
    probe_url = final_url if final_url else (f"https://doi.org/{doi}" if doi else "")
    doi_url = f"https://doi.org/{doi}" if doi else probe_url

    # Verificação por domínio: alguns domínios OA são sabidamente bloqueados
    for domain in _BOT_PROTECTED_OA_DOMAINS:
        if domain in (final_url or "").lower():
            return {
                "type": "bot_protect",
                "label": "OA bloqueado por bot (abra no navegador)",
                "url": probe_url,
                "detail": f"Domínio OA com proteção anti-bot: {domain}",
            }

    if not probe_url:
        return {
            "type": "no_url",
            "label": "Sem URL disponível",
            "url": doi_url,
            "detail": reason,
        }

    # [v7] Se o motivo registrado já diz que o circuit breaker desativou o
    # host, não há o que sondar — e sondar seria exatamente o tráfego que
    # o breaker existe para evitar.
    if "host bloqueado" in reason or "desativado nesta execução" in reason:
        return {
            "type": "blocked_run",
            "label": "Host bloqueou durante a execução — tente mais tarde",
            "url": doi_url,
            "detail": reason[:80],
        }

    # [v7] --no-probe: classificação offline pelo motivo registrado.
    # Menos precisa que a sondagem (403 pode ser bot OU paywall), mas
    # não gera nenhuma requisição nova.
    if not probe:
        if "HTTP 403" in reason:
            return {
                "type": "paywall",
                "label": "403 no download — paywall ou anti-bot (confira no navegador)",
                "url": doi_url,
                "detail": reason[:80],
            }
        if "retornou HTML" in reason:
            return {
                "type": "html_ok",
                "label": "Página HTML acessível (PDF não extraído)",
                "url": probe_url,
                "detail": reason[:80],
            }
        return {
            "type": "server_error",
            "label": "Não baixado (diagnóstico offline — --no-probe)",
            "url": doi_url,
            "detail": reason[:80],
        }

    # Requisição leve para classificar a resposta atual
    try:
        r = polite_get(probe_url, timeout=15, allow_redirects=True, stream=True)
        # Lê apenas os primeiros 2 KB para detectar marcadores no corpo.
        # [v7] Via iter_content, que DESCOMPRIME o corpo: r.raw.read()
        # devolvia bytes gzip/brotli (Accept-Encoding da sessão) e os
        # marcadores anti-bot nunca casavam — todo 403 virava "paywall".
        body_preview = next(r.iter_content(chunk_size=2048), b"")
        r.close()  # [v7] só precisamos do preview

        if r.status_code == 403:
            # Verificar corpo por marcadores bot
            if any(m in body_preview for m in _BOT_BODY_MARKERS):
                return {
                    "type": "bot_protect",
                    "label": "OA bloqueado por bot (abra no navegador)",
                    "url": r.url,
                    "detail": f"HTTP 403 + marcador anti-bot detectado",
                }
            return {
                "type": "paywall",
                "label": "Paywall — acesse via CAPES/CAFe",
                "url": doi_url,
                "detail": f"HTTP 403 — acesso restrito",
            }

        if r.status_code in (401, 402):
            return {
                "type": "paywall",
                "label": "Paywall — acesse via CAPES/CAFe",
                "url": doi_url,
                "detail": f"HTTP {r.status_code}",
            }

        if r.status_code == 200:
            ct = r.headers.get("Content-Type", "").lower()
            if "text/html" in ct:
                return {
                    "type": "html_ok",
                    "label": "Página HTML acessível (PDF não extraído)",
                    "url": r.url,
                    "detail": "200 HTML — tente abrir no navegador",
                }
            # Pode ser PDF protegido por login que retorna 200 mas HTML
            if any(m in body_preview for m in _BOT_BODY_MARKERS):
                return {
                    "type": "bot_protect",
                    "label": "OA bloqueado por bot (abra no navegador)",
                    "url": r.url,
                    "detail": "200 com corpo de bloqueio anti-bot",
                }
            return {
                "type": "html_ok",
                "label": "Página acessível (PDF não extraído)",
                "url": r.url,
                "detail": f"HTTP 200 — {ct[:40]}",
            }

        if r.status_code >= 500:
            return {
                "type": "server_error",
                "label": "Erro de servidor",
                "url": doi_url,
                "detail": f"HTTP {r.status_code}",
            }

        return {
            "type": "server_error",
            "label": "Erro / URL expirada",
            "url": doi_url,
            "detail": f"HTTP {r.status_code}",
        }

    except HostBlockedError:
        # [v7] O host da sondagem está desativado nesta execução — antes
        # caía no except genérico e virava "Erro de rede / URL inválida",
        # degradando o relatório inteiro quando um host popular bloqueava.
        return {
            "type": "blocked_run",
            "label": "Host bloqueou durante a execução — tente mais tarde",
            "url": doi_url,
            "detail": "circuit breaker aberto para este host",
        }
    except requests.Timeout:
        return {
            "type": "server_error",
            "label": "Timeout — servidor lento ou URL inválida",
            "url": doi_url,
            "detail": "Timeout na requisição de diagnóstico",
        }
    except requests.RequestException as e:
        return {
            "type": "server_error",
            "label": "Erro de rede / URL inválida",
            "url": doi_url,
            "detail": str(e)[:60],
        }


def generate_html_report(
    failed_items: list[dict],
    output_path: Path,
    bib_path: str,
    total_entries: int,
    downloaded: int,
    elapsed: float,
    blocked_hosts: set[str] | None = None,     # [v7] hosts que bloquearam
    api_unavailable: set[str] | None = None,   # [v7] APIs indisponíveis
) -> None:
    """
    [v5] Gera relatório HTML de diagnóstico para artigos não baixados.

    O relatório contém as seções:
      1. OA bloqueado por bot — links diretos, clique e baixe
      2. Paywall real — links para Portal CAPES/CAFe
      3. [v7] Hosts que bloquearam durante a execução — tentar mais tarde
      4. Outros erros — erros de servidor, URLs inválidas, etc.

    [v7] Todo campo vindo do .bib ou da rede passa por html.escape —
    título com < ou & quebrava o layout da página. A lista de hosts
    bloqueados/APIs indisponíveis agora também entra no HTML (antes só
    aparecia no stdout, que some quando o terminal fecha).

    Args:
        failed_items:  Lista de dicts produzidos por classify_failure,
                       cada um com chaves extras "key", "title", "doi",
                       "authors", "year", "reason"
        output_path:   Caminho completo do arquivo .html a ser criado
        bib_path:      Caminho do .bib de entrada (para o cabeçalho)
        total_entries: Total de entradas no .bib
        downloaded:    Quantidade de PDFs baixados com sucesso
        elapsed:       Tempo de execução em segundos
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    def esc(s) -> str:
        """[v7] html.escape em tudo que vem do .bib ou da rede."""
        return html.escape(str(s), quote=True)

    bot = [x for x in failed_items if x["type"] == "bot_protect"]
    paywall = [x for x in failed_items if x["type"] == "paywall"]
    html_ok = [x for x in failed_items if x["type"] == "html_ok"]
    blocked = [x for x in failed_items if x["type"] == "blocked_run"]  # [v7]
    errors = [x for x in failed_items if x["type"] in ("server_error", "no_url")]

    def _entry_card(item: dict, link_label: str, link_class: str) -> str:
        # [v7] esc() em todos os campos — eram interpolados crus no HTML
        title = esc(item.get("title", "Sem título"))
        authors = esc(item.get("authors", ""))
        year = esc(item.get("year", ""))
        key = esc(item.get("key", ""))
        doi = esc(item.get("doi", ""))
        url = esc(item.get("url", ""))
        detail = esc(item.get("detail", ""))
        doi_url = f"https://doi.org/{doi}" if doi else ""

        authors_year = f"{authors}, {year}".strip(", ")

        card = f"""
        <div class="card">
          <div class="card-key">{key}</div>
          <div class="card-title">{title}</div>
          <div class="card-meta">{authors_year}</div>"""

        if doi:
            card += f'\n          <div class="card-doi">DOI: <a href="{doi_url}" target="_blank">{doi}</a></div>'

        if url:
            card += f'\n          <a class="btn {link_class}" href="{url}" target="_blank">{link_label}</a>'
        elif doi_url:
            card += f'\n          <a class="btn {link_class}" href="{doi_url}" target="_blank">{link_label}</a>'

        if detail:
            card += f'\n          <div class="card-detail">{detail}</div>'

        card += "\n        </div>"
        return card

    def _section(title: str, icon: str, items: list[dict], link_label: str,
                 link_class: str, description: str) -> str:
        if not items:
            return ""
        cards = "\n".join(_entry_card(x, link_label, link_class) for x in items)
        return f"""
      <section>
        <h2>{icon} {title} <span class="badge">{len(items)}</span></h2>
        <p class="section-desc">{description}</p>
        {cards}
      </section>"""

    bot_section = _section(
        "OA bloqueado por bot — baixe agora", "⬇️", bot,
        "Abrir artigo", "btn-green",
        "Estes artigos são de <strong>acesso aberto</strong>, mas o servidor bloqueia "
        "downloads automáticos. Clique no botão para abrir no navegador e use "
        "<em>Ctrl+S</em> ou o botão de download da página.",
    )
    paywall_section = _section(
        "Paywall real — acesse via CAPES/CAFe", "🔒", paywall,
        "Acessar via CAPES", "btn-blue",
        "Estes artigos estão atrás de paywall. Acesse via "
        "<a href='https://periodicos.capes.gov.br' target='_blank'>Portal CAPES/CAFe</a> "
        "ou pesquise o título no Google Scholar para encontrar versões OA.",
    )
    html_section = _section(
        "Página HTML acessível — PDF não extraído", "🌐", html_ok,
        "Abrir página", "btn-orange",
        "O servidor retornou uma página HTML acessível, mas o script não conseguiu "
        "extrair o link direto para o PDF. Abra a página no navegador e procure o "
        "botão de download do PDF.",
    )
    error_section = _section(
        "Erros de servidor / sem cobertura", "⚠️", errors,
        "Tentar DOI", "btn-gray",
        "Erros técnicos: timeout, servidor fora do ar, URL expirada, ou artigo sem "
        "DOI. Tente acessar via DOI ou pesquise manualmente.",
    )
    # [v7] Categoria nova: artigos que falharam porque o circuit breaker
    # desativou o host no meio da execução. Não é paywall nem erro — é
    # "rode o script de novo mais tarde".
    blocked_section = _section(
        "Host bloqueou durante a execução — tente mais tarde", "⏸️", blocked,
        "Abrir DOI", "btn-gray",
        "O servidor destes artigos respondeu 429/403 repetidamente e foi "
        "desativado pelo resto da execução para não agravar o bloqueio. "
        "<strong>Espere algumas horas e rode o script de novo</strong> — "
        "estes artigos nem chegaram a ser tentados até o fim.",
    )

    # [v7] Resumo de hosts bloqueados / APIs indisponíveis também no HTML
    # (antes essa informação existia só no stdout).
    hosts_box = ""
    if blocked_hosts or api_unavailable:
        rows = ""
        for h in sorted(blocked_hosts or []):
            rows += f"<li><code>{esc(h)}</code> — bloqueou (429/403); espere antes de rodar de novo</li>\n"
        for h in sorted(api_unavailable or []):
            rows += f"<li><code>{esc(h)}</code> — API indisponível (cota/chave); costuma normalizar sozinho</li>\n"
        hosts_box = f"""
    <div class="hosts-box">
      <strong>⛔ Hosts com problema nesta execução:</strong>
      <ul>{rows}</ul>
    </div>"""

    capes_url = "https://periodicos.capes.gov.br"
    # [v7] Variável renomeada de "html" para "html_doc": o módulo stdlib
    # html (usado no esc() acima) está importado e o nome colidia — dentro
    # desta função, html.escape resolveria para a string local, não para o
    # módulo, e quebraria com NameError.
    html_doc = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>BibFix v8 — Relatório de Download</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f5f5f7; color: #1d1d1f; line-height: 1.5; }}
    header {{ background: #1d1d1f; color: #fff; padding: 28px 40px; }}
    header h1 {{ font-size: 1.5rem; font-weight: 600; }}
    header .subtitle {{ color: #a1a1a6; font-size: 0.9rem; margin-top: 6px; }}
    .stats {{ display: flex; gap: 24px; margin-top: 16px; flex-wrap: wrap; }}
    .stat {{ background: rgba(255,255,255,.08); border-radius: 8px;
             padding: 10px 18px; }}
    .stat-n {{ font-size: 1.8rem; font-weight: 700; }}
    .stat-l {{ font-size: 0.75rem; color: #a1a1a6; text-transform: uppercase;
               letter-spacing: .05em; }}
    main {{ max-width: 900px; margin: 40px auto; padding: 0 24px 60px; }}
    section {{ margin-bottom: 48px; }}
    h2 {{ font-size: 1.15rem; margin-bottom: 8px; display: flex;
          align-items: center; gap: 8px; }}
    .badge {{ background: #e5e5ea; color: #3a3a3c; border-radius: 20px;
              font-size: 0.8rem; padding: 2px 10px; font-weight: 600; }}
    .section-desc {{ color: #6e6e73; font-size: 0.88rem; margin-bottom: 16px;
                     line-height: 1.6; }}
    .section-desc a {{ color: #0071e3; }}
    .card {{ background: #fff; border-radius: 12px; padding: 18px 20px;
             margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
    .card-key {{ font-size: 0.75rem; color: #8e8e93; font-family: monospace;
                 margin-bottom: 4px; }}
    .card-title {{ font-weight: 600; font-size: 0.97rem; margin-bottom: 4px; }}
    .card-meta {{ font-size: 0.82rem; color: #6e6e73; margin-bottom: 6px; }}
    .card-doi {{ font-size: 0.82rem; color: #6e6e73; margin-bottom: 8px; }}
    .card-doi a {{ color: #0071e3; text-decoration: none; }}
    .card-doi a:hover {{ text-decoration: underline; }}
    .card-detail {{ font-size: 0.75rem; color: #aeaeb2; margin-top: 8px;
                    font-family: monospace; }}
    .btn {{ display: inline-block; padding: 7px 16px; border-radius: 8px;
            font-size: 0.85rem; font-weight: 500; text-decoration: none;
            margin-top: 4px; }}
    .btn-green  {{ background: #34c759; color: #fff; }}
    .btn-blue   {{ background: #0071e3; color: #fff; }}
    .btn-orange {{ background: #ff9f0a; color: #fff; }}
    .btn-gray   {{ background: #e5e5ea; color: #3a3a3c; }}
    .btn:hover  {{ opacity: .85; }}
    footer {{ text-align: center; color: #aeaeb2; font-size: 0.8rem;
              padding: 24px; }}
    /* [v7] caixa de hosts bloqueados */
    .hosts-box {{ background: #fff3cd; border: 1px solid #ffe69c;
                  border-radius: 12px; padding: 16px 20px; margin-bottom: 40px;
                  font-size: 0.88rem; }}
    .hosts-box ul {{ margin: 8px 0 0 20px; }}
    .hosts-box code {{ background: rgba(0,0,0,.06); padding: 1px 6px;
                       border-radius: 4px; }}
    .capes-banner {{ background: #0071e3; color: #fff; border-radius: 12px;
                     padding: 16px 20px; margin-bottom: 40px; }}
    .capes-banner a {{ color: #ffd60a; font-weight: 600; }}
  </style>
</head>
<body>
  <header>
    <h1>BibFix v8 — Relatório de Download</h1>
    <div class="subtitle">{esc(bib_path)} &nbsp;·&nbsp; {now}</div>
    <div class="stats">
      <div class="stat"><div class="stat-n">{total_entries}</div>
        <div class="stat-l">referências</div></div>
      <div class="stat"><div class="stat-n" style="color:#30d158">{downloaded}</div>
        <div class="stat-l">baixados</div></div>
      <div class="stat"><div class="stat-n" style="color:#ff453a">{len(failed_items)}</div>
        <div class="stat-l">não baixados</div></div>
      <div class="stat"><div class="stat-n">{elapsed/60:.1f} min</div>
        <div class="stat-l">tempo</div></div>
    </div>
  </header>
  <main>
    <div class="capes-banner">
      💡 Para artigos em paywall, acesse via
      <a href="{capes_url}" target="_blank">Portal CAPES/CAFe</a>
      com login institucional.
    </div>
    {hosts_box}
    {bot_section}
    {paywall_section}
    {html_section}
    {blocked_section}
    {error_section}
  </main>
  <footer>Gerado por BibFix v8 &nbsp;·&nbsp; {now}</footer>
</body>
</html>"""

    output_path.write_text(html_doc, encoding="utf-8")


# ============================================================================
# INTERFACE E EXECUÇÃO PRINCIPAL
# ============================================================================


def _load_local_config() -> dict[str, str]:
    """
    [v7] Lê o arquivo de credenciais local (CONFIG_FILE, ao lado do script)
    no formato `chave = valor` por linha. Linhas em branco e começando com #
    são ignoradas; tudo antes do primeiro `=` é a chave (minúscula), o resto
    é o valor. Retorna {} se o arquivo não existir ou não puder ser lido.

    Existe para manter dados pessoais (e-mail de contato, chave de API) FORA
    do código, de modo que o script possa ser compartilhado sem editar o
    fonte. Chaves reconhecidas hoje: 'email', 'openalex_key'.
    """
    cfg: dict[str, str] = {}
    path = Path(__file__).resolve().parent / CONFIG_FILE
    if not path.exists():
        return cfg
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            raw_key = key.strip().lower()
            value = value.strip()  # espaços em volta do "=" e do valor somem
            # [v7] Tolera o valor entre aspas ("...", '...') ou chaves ({...}) —
            # engano comum de quem vem do BibTeX, onde os campos ficam em {}.
            # E-mail e chave de API nunca contêm esses caracteres, então
            # removê-los das bordas é seguro. Remove pares casados, inclusive
            # aninhados (ex.: {{x}} → x).
            while len(value) >= 2 and (value[0], value[-1]) in (
                    ('"', '"'), ("'", "'"), ("{", "}")):
                value = value[1:-1].strip()
            # [v7] normaliza apelidos (chave_openalex → openalex_key etc.)
            canonical = _CONFIG_KEY_ALIASES.get(raw_key, raw_key)
            cfg[canonical] = value
    except OSError:
        pass
    return cfg


def _resolve_setting(cli_value: str | None, env_var: str,
                     cfg_key: str, cfg: dict[str, str]) -> str:
    """
    [v7] Resolve uma configuração na ordem de precedência:
      1. valor da linha de comando (--flag)
      2. variável de ambiente `env_var`
      3. arquivo de credenciais local (chave `cfg_key`)
    Retorna "" se nenhuma fonte definir o valor.
    """
    if cli_value:
        return cli_value.strip()
    env = os.environ.get(env_var, "").strip()
    if env:
        return env
    return cfg.get(cfg_key, "").strip()


def parse_args() -> argparse.Namespace:
    """
    Parseia argumentos de linha de comando.

    [v5] --no-report : desabilita o relatório HTML de diagnóstico
    [v6] --doi-scrape / --delay : controles de tráfego
    [v7] --no-probe : diagnóstico sem requisições extras
    [v7] Validação de faixa para --threshold e --delay: antes, valores como
         --threshold 5 ou --delay -2 passavam calados (o delay negativo
         estourava num ValueError do time.sleep no meio da execução).
    [v8] --no-doi-discovery : não busca DOI no Crossref para entradas sem DOI
    [v8] --use-doi-as-filename : nomeia o arquivo pelo DOI em vez de Autor-Ano
    """
    parser = argparse.ArgumentParser(
        description="BibFix v8 - Download de PDFs acadêmicos de acesso aberto.",
    )
    parser.add_argument(
        "--bib", default=DEFAULT_BIB_INPUT,
        help=f"Arquivo .bib de entrada (default: {DEFAULT_BIB_INPUT})",
    )
    parser.add_argument(
        "--output", default=DEFAULT_PDF_DIR,
        help=f"Pasta para salvar PDFs (default: {DEFAULT_PDF_DIR})",
    )
    # [v7] default None para distinguir "não passou" de "passou". A resolução
    # (CLI > env BIBGETPDF_EMAIL > arquivo de config) acontece após o parse.
    parser.add_argument(
        "--email", default=None,
        help="E-mail de contato para as APIs acadêmicas (Unpaywall exige um; "
             "os demais usam para o 'polite pool'). Se omitido, vem da "
             "variável de ambiente BIBGETPDF_EMAIL ou do arquivo "
             f"'{CONFIG_FILE}' (chave: email).",
    )
    # [v7] Chave da API OpenAlex. Mesma cadeia de resolução do e-mail.
    parser.add_argument(
        "--openalex-key", default=None,
        help="Chave da API OpenAlex (obrigatória desde 13/02/2026 para não "
             "cair no limite de ~100 req/dia). Se omitida, vem da variável "
             f"de ambiente OPENALEX_API_KEY ou do arquivo '{CONFIG_FILE}' "
             "(chave: openalex_key). Key gratuita em openalex.org/settings/api.",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.75,
        help="Limiar de similaridade fuzzy para busca por título "
             "(0.0-1.0, default: 0.75). Valores maiores = mais estrito.",
    )
    # [v5] Opção para desabilitar o relatório HTML
    parser.add_argument(
        "--no-report", action="store_true",
        help="Não gerar relatório HTML de diagnóstico ao final.",
    )
    # [v6] Controles de tráfego
    parser.add_argument(
        "--doi-scrape", action="store_true",
        help="Reativa a fonte DOI-PDF, que raspa landing pages de editora. "
             "Aumenta a cobertura em poucos artigos e é a principal causa "
             "de bloqueio de IP. Desligada por padrão.",
    )
    parser.add_argument(
        "--delay", type=float, default=3.0,
        help="Pausa em segundos entre artigos (default: 3.0). "
             "Aumente se o IP já tiver sido bloqueado antes.",
    )
    # [v7] Diagnóstico sem requisições extras
    parser.add_argument(
        "--no-probe", action="store_true",
        help="No diagnóstico do relatório, não fazer nenhuma requisição "
             "extra — classifica as falhas só pelo motivo registrado "
             "durante o download.",
    )
    # [v8] Descoberta de DOI no Crossref (ligada por padrão)
    parser.add_argument(
        "--no-doi-discovery", action="store_true",
        help="Não tentar descobrir o DOI no Crossref para entradas sem DOI. "
             "Por padrão, entradas sem DOI são buscadas por título+autor no "
             "Crossref (1 requisição extra por entrada sem DOI); só um match "
             "validado (título+sobrenome+ano) é aceito.",
    )
    # [v8] Nome de arquivo pelo DOI
    parser.add_argument(
        "--use-doi-as-filename", action="store_true",
        help="Nomear o PDF pelo DOI (ex.: 10.1016_j.cell...pdf) em vez de "
             "Sobrenome-Ano-Titulo. Útil para títulos ambíguos/repetidos. "
             "Entradas sem DOI seguem no padrão Sobrenome-Ano-Titulo.",
    )

    args = parser.parse_args()

    # [v7] Validação de faixa — falha cedo, com mensagem do argparse.
    if not (0.0 < args.threshold <= 1.0):
        parser.error("--threshold deve estar entre 0 (exclusivo) e 1")
    if args.delay < 0:
        parser.error("--delay não pode ser negativo")

    # [v7] Resolve e-mail e chave num só lugar (CLI > env > arquivo de
    # config). O e-mail cai no placeholder DEFAULT_EMAIL se nada for
    # definido — o main detecta esse placeholder e avisa antes de rodar.
    cfg = _load_local_config()
    args.email = _resolve_setting(
        args.email, "BIBGETPDF_EMAIL", "email", cfg) or DEFAULT_EMAIL
    args.openalex_key = _resolve_setting(
        args.openalex_key, "OPENALEX_API_KEY", "openalex_key", cfg)

    return args


def print_header(start_time: datetime) -> None:
    """Imprime cabeçalho com versão, hora e lista de fontes."""
    print("=" * 70)
    print("  BibFix - Download de PDFs v8")  # [v8] dizia v7
    print(f"  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()
    print("  Fontes (em ordem):")
    print("    1. Unpaywall       — base global de open access")
    print("    2. Semantic Scholar — API com openAccessPdf")
    print("    3. OpenAlex        — base aberta de metadados")
    print("    4. Europe PMC      — REST API direta (biomédicos)")
    print("    5. PMC             — PubMed Central via NCBI (fallback)")
    print("    6. arXiv           — preprints CS/física/matemática/bio")
    print("    7. CORE            — repositórios institucionais")
    print("    8. DOAJ            — journals open access verificados")
    print("    9. DOI-PDF         — redirect + padrões por editora")
    print("       [v6] desligada por padrão — reative com --doi-scrape")
    print("       (ScienceDirect, Springer, IEEE, ACM, BMJ, JAMA,")
    print("        Nature, Lancet, Wiley, SAGE, T&F, PNAS, Oxford,")
    print("        Cambridge, Emerald, De Gruyter, MDPI, Frontiers,")
    print("        PLOS, BMC, PeerJ, Hindawi, SciELO,")
    print("        RSC, ACS, Karger, LWW)")
    print("   10. SciELO          — periódicos latino-americanos")
    print()
    bs4_status = "instalado" if _BS4_AVAILABLE else "não instalado (opcional)"
    print(f"  BeautifulSoup: {bs4_status}")
    print(f"  Relatório HTML de diagnóstico: habilitado")  # [v7] dizia [v5]
    print()


def print_summary(
    stats: dict[str, int],
    source_stats: dict[str, int],
    elapsed: float,
    pdf_dir: Path,
) -> None:
    """Imprime resumo final da execução no terminal."""
    print("\n" + "=" * 70)
    print("  📊 RESUMO")
    print("=" * 70)
    print(f"  ✅ Baixados:           {stats['baixado']}")
    if source_stats:
        for src, count in sorted(source_stats.items(), key=lambda x: -x[1]):
            print(f"     └─ via {src:<14s}  {count}")
    if stats.get("doi_descoberto"):  # [v8]
        print(f"  🔎 DOIs descobertos:   {stats['doi_descoberto']} (Crossref)")
    print(f"  ⏭️  Já existiam:       {stats['existe']}")
    print(f"  ⚠️  Sem DOI:           {stats['sem_doi']}")
    print(f"  🔒 Não disponíveis:    {stats['nao_encontrado']}")
    print(f"  ❌ Erros:              {stats['erro']}")
    print(f"  📁 Pasta:              {pdf_dir.absolute()}")
    print(f"  ⏱️  Tempo:              {elapsed:.1f}s ({elapsed / 60:.1f} min)")


def save_log(
    log_file: Path,
    results: list[tuple[str, str, str, str]],
    stats: dict[str, int],
    source_stats: dict[str, int],
    error_details: list[tuple[str, str]],
    entries: list[dict],
    elapsed: float,
) -> None:
    """
    Salva log detalhado em arquivo texto com 4 seções:
      1. Resultados detalhados por entrada
      2. Resumo com contadores
      3. Detalhes dos erros
      4. Lista para download manual (CAPES/CAFe)
    """
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("BibFix - Log de Download v8\n")  # [v8] dizia v7
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'=' * 70}\n\n")

        f.write("RESULTADOS DETALHADOS\n")
        f.write(f"{'-' * 70}\n")
        for key, status, source, filename in results:
            src_str = f"[{source}]" if source else ""
            f.write(f"  {status:<18s} {src_str:<14s} {key:<30s} {filename}\n")

        f.write(f"\n{'=' * 70}\n")
        f.write("RESUMO\n")
        f.write(f"  Baixados:        {stats['baixado']}\n")
        if source_stats:
            for src, count in sorted(source_stats.items(), key=lambda x: -x[1]):
                f.write(f"    via {src}: {count}\n")
        if stats.get("doi_descoberto"):  # [v8]
            f.write(f"  DOIs descobertos:{stats['doi_descoberto']:>2} (Crossref)\n")
        f.write(f"  Já existiam:     {stats['existe']}\n")
        f.write(f"  Sem DOI:         {stats['sem_doi']}\n")
        f.write(f"  Não disponíveis: {stats['nao_encontrado']}\n")
        f.write(f"  Erros:           {stats['erro']}\n")
        f.write(f"  Tempo:           {elapsed:.1f}s\n")

        if error_details:
            f.write(f"\n{'=' * 70}\n")
            f.write("DETALHES DOS ERROS\n")
            f.write(f"{'-' * 70}\n")
            for key, reason in error_details:
                f.write(f"  [{key}]\n    Motivo: {reason}\n\n")

        # [v7] Hosts bloqueados/APIs indisponíveis também no log — antes a
        # informação só existia no stdout, que some quando o terminal fecha.
        real_blocks = _blocked_hosts - _api_unavailable
        if real_blocks or _api_unavailable:
            f.write(f"\n{'=' * 70}\n")
            f.write("HOSTS COM PROBLEMA NESTA EXECUÇÃO\n")
            f.write(f"{'-' * 70}\n")
            for h in sorted(real_blocks):
                f.write(f"  ⛔ {h} — bloqueou (429/403); espere antes de rodar de novo\n")
            for h in sorted(_api_unavailable):
                f.write(f"  ⓘ  {h} — API indisponível (cota/chave); normaliza sozinho\n")

        missing = [r for r in results if r[1] in ("não encontrado", "sem DOI", "erro")]
        if missing:
            f.write(f"\n{'=' * 70}\n")
            f.write(f"ARTIGOS PARA DOWNLOAD MANUAL ({len(missing)})\n")
            f.write("Baixe via Portal CAPES/CAFe: https://periodicos.capes.gov.br\n")
            f.write(f"{'-' * 70}\n")
            for key, status, _, _ in missing:
                for e in entries:
                    if e.get("ID") == key:
                        doi_val = e.get("doi", "sem DOI")
                        title = e.get("title", "")[:70].replace("{", "").replace("}", "")
                        f.write(f"  [{key}]\n")
                        f.write(f"    Título: {title}\n")
                        f.write(f"    DOI:    {doi_val}\n")
                        if doi_val and doi_val != "sem DOI":
                            f.write(f"    Link:   https://doi.org/{doi_val}\n")
                        f.write(f"    Status: {status}\n\n")
                        break



def main() -> None:
    """
    Fluxo principal do BibFix v8.

    Etapas:
      1. Parsear argumentos (--bib, --output, --email, --threshold,
         --no-report, --doi-scrape, --delay, --no-probe,
         [v8] --no-doi-discovery, --use-doi-as-filename)
      2. Validar arquivo .bib e email
      3. Carregar .bib e exibir estatísticas
      4. Criar pasta de saída ([v7] limpando sobras .part de execuções
         interrompidas)
      5. Para cada entrada: [v8] descobrir o DOI no Crossref se faltar, então
         baixar o PDF (sequencial; [v7] PDFs existentes são REVALIDADOS antes
         de pular — corrompido é baixado de novo)
      6. Imprimir resumo
      7. Salvar log detalhado ([v7] hosts bloqueados) e [v8] manifest.csv
      8. [v5] Diagnóstico dos artigos não baixados (~1 req por artigo;
         [v7] nenhuma com --no-probe)
      9. [v5] Gerar relatório HTML com links e classificação de falhas
    """
    args = parse_args()
    bib_input = args.bib
    pdf_output = args.output
    config = Config(
        email=args.email,
        title_match_threshold=args.threshold,
        enable_doi_scrape=args.doi_scrape,
        delay_between_entries=args.delay,
        probe_failures=not args.no_probe,  # [v7]
        openalex_api_key=args.openalex_key,  # [v7]
        enable_doi_discovery=not args.no_doi_discovery,  # [v8]
        use_doi_as_filename=args.use_doi_as_filename,     # [v8]
    )
    generate_report = not args.no_report

    start_time = datetime.now()
    print_header(start_time)

    # [v7] Aviso sobre a fonte OpenAlex sem key (limitada a ~100 req/dia
    # desde 13/02/2026). Só avisa — não impede a execução; as outras 9
    # fontes seguem normalmente.
    if config.openalex_api_key:
        print("🔑 OpenAlex: usando API key fornecida.\n")
    else:
        print("⚠️  OpenAlex sem API key — fonte limitada a ~100 req/dia "
              "(mudança de 13/02/2026).\n"
              "    Defina OPENALEX_API_KEY ou use --openalex-key. "
              "Key gratuita: openalex.org/settings/api\n")

    if not Path(bib_input).exists():
        print(f"❌ Arquivo não encontrado: {bib_input}")
        return

    if config.email == DEFAULT_EMAIL:
        print("⚠️  Nenhum e-mail de contato configurado — as APIs acadêmicas "
              "precisam de um (a Unpaywall exige).\n"
              "    Defina de UMA destas formas:\n"
              "      • --email voce@exemplo.com\n"
              "      • variável de ambiente BIBGETPDF_EMAIL\n"
              f"      • arquivo '{CONFIG_FILE}' com a linha:  email = voce@exemplo.com")
        return

    # [v7] E-mail confirmado como real: reescreve o User-Agent da sessão de
    # APIs com ele (a constante UA_ACADEMIC nasce só com um placeholder). É o
    # que identifica quem roda nos 'polite pools' e no contato das APIs.
    API_SESSION.headers["User-Agent"] = (
        f"BibFix/8.0 (academic PDF downloader; mailto:{config.email})"
    )

    print(f"📂 Carregando: {bib_input}")
    bib_db = load_bib(bib_input)
    entries = bib_db.entries
    print(f"   Entradas: {len(entries)}")
    with_doi = sum(1 for e in entries if e.get("doi", "").strip())
    print(f"   Com DOI:  {with_doi}")
    n_sem_doi = len(entries) - with_doi
    print(f"   Sem DOI:  {n_sem_doi}")
    # [v8] Estado da descoberta de DOI — é o que vai atrás dos artigos sem DOI.
    if config.enable_doi_discovery:
        if n_sem_doi:
            print(f"   🔎 Descoberta de DOI (Crossref) ativa para as {n_sem_doi} "
                  f"sem DOI  (--no-doi-discovery desliga)")
    else:
        print("   🔎 Descoberta de DOI desativada (--no-doi-discovery)")
    if config.use_doi_as_filename:
        print("   🏷️  Arquivos nomeados pelo DOI (--use-doi-as-filename)")
    if args.threshold != 0.75:
        print(f"   Threshold fuzzy: {args.threshold}")

    pdf_dir = Path(pdf_output)
    if pdf_dir.exists():
        existing = list(pdf_dir.glob("*.pdf"))
        print(f"\n📁 Pasta '{pdf_output}' já existe ({len(existing)} PDFs)")
        # [v7] Varre sobras .part de execuções interrompidas (o download
        # atômico escreve nelas e renomeia no fim; se sobrou, é lixo).
        for leftover in pdf_dir.glob("*.part"):
            leftover.unlink(missing_ok=True)
    else:
        pdf_dir.mkdir(parents=True)
        print(f"\n📁 Pasta '{pdf_output}' criada")

    print("\n" + "=" * 70)
    print("  📥 BUSCANDO PDFs")
    print("=" * 70 + "\n")

    stats: dict[str, int] = {
        "baixado": 0, "existe": 0, "sem_doi": 0, "nao_encontrado": 0, "erro": 0,
        "doi_descoberto": 0,  # [v8] DOIs preenchidos pela descoberta no Crossref
    }
    source_stats: dict[str, int] = {}
    results: list[tuple[str, str, str, str]] = []
    error_details: list[tuple[str, str]] = []

    # [v5] Dados extras para diagnóstico: (entry, final_url, reason)
    failed_entries: list[tuple[dict, str, str]] = []

    total = len(entries)
    discovered_keys: set[str] = set()  # [v8] entradas cujo DOI veio do Crossref

    for i, entry in enumerate(entries, 1):
        key = entry.get("ID", "?")
        print(f"  [{i:3d}/{total}] {key[:40]:<40s}", end=" ", flush=True)

        # [v8] Descoberta de DOI (Crossref) para entradas sem DOI, ANTES de
        # definir o nome do arquivo: o DOI descoberto alimenta o nome (com
        # --use-doi-as-filename), todas as fontes por DOI e o diagnóstico/
        # manifesto. Injetado direto na entrada (dict mutável). No resume, uma
        # entrada já baixada pode gastar 1 chamada extra ao Crossref aqui — é
        # raro e barato, e mantém o nome do arquivo coerente com o DOI.
        if config.enable_doi_discovery and not entry.get("doi", "").strip():
            found = try_crossref_doi(
                entry, config.email, config.title_match_threshold)
            if found:
                entry["doi"] = found  # injeta → fontes por DOI voltam ao jogo
                discovered_keys.add(key)
                stats["doi_descoberto"] += 1
                print("🔎 ", end="", flush=True)

        filename = make_filename(entry, use_doi=config.use_doi_as_filename)
        filepath = pdf_dir / filename

        if filepath.exists():
            # [v7] Revalidar antes de pular: um PDF corrompido (download
            # interrompido por versões antigas, HTML salvo como .pdf) era
            # pulado para sempre pelo resume. A checagem é local e barata.
            if is_valid_pdf(filepath):
                print("⏭️  já existe")
                stats["existe"] += 1
                results.append((key, "já existe", "", filename))
                continue
            print("♻️  existia corrompido → ", end="", flush=True)
            filepath.unlink()

        has_doi = bool(entry.get("doi", "").strip())
        success, source, reason, final_url = find_and_download(entry, filepath, config)

        if success:
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"✅ [{source}] {size_mb:.1f} MB")
            stats["baixado"] += 1
            source_stats[source] = source_stats.get(source, 0) + 1
            results.append((key, "baixado", source, filename))
        elif not has_doi and "nenhuma URL" in reason:
            print("⚠️  sem DOI")
            stats["sem_doi"] += 1
            results.append((key, "sem DOI", "", ""))
            failed_entries.append((entry, final_url, reason))
        elif "nenhuma URL" in reason:
            print("🔒 não disponível")
            stats["nao_encontrado"] += 1
            results.append((key, "não encontrado", "", ""))
            failed_entries.append((entry, final_url, reason))
        else:
            short = reason[:60] if len(reason) > 60 else reason
            print(f"❌ {short}")
            stats["erro"] += 1
            results.append((key, "erro", source, ""))
            error_details.append((key, reason))
            failed_entries.append((entry, final_url, reason))

        time.sleep(config.delay_between_entries)

    # ---- Resumo e log ----
    elapsed = (datetime.now() - start_time).total_seconds()
    print_summary(stats, source_stats, elapsed, pdf_dir)

    log_file = pdf_dir / "download_log.txt"
    save_log(log_file, results, stats, source_stats, error_details, entries, elapsed)
    print(f"  📄 Log salvo:          {log_file}")

    # [v8] Manifesto CSV do lote: uma linha por entrada, para abrir no
    # Excel/LibreOffice e revisar o que baixou/faltou. entries e results ficam
    # alinhados — cada iteração do loop acrescenta exatamente uma tupla a
    # results, na mesma ordem de entries.
    manifest_file = pdf_dir / "manifest.csv"
    reason_by_key = {e.get("ID", "?"): reason
                     for e, _url, reason in failed_entries}
    try:
        with open(manifest_file, "w", encoding="utf-8", newline="") as mf:
            writer = csv.writer(mf)
            writer.writerow([
                "chave", "status", "fonte", "doi", "doi_descoberto",
                "ano", "sobrenome", "titulo", "arquivo", "motivo",
            ])
            for entry, (rkey, status, source, filename) in zip(entries, results):
                doi = clean_doi(entry.get("doi", "")) if entry.get("doi") else ""
                title = (entry.get("title", "") or "").replace(
                    "{", "").replace("}", "").strip()
                writer.writerow([
                    rkey, status, source, doi,
                    "sim" if rkey in discovered_keys else "",
                    (entry.get("year", "") or "").strip(),
                    _first_author_surname(entry.get("author", "")),
                    title, filename,
                    reason_by_key.get(rkey, ""),
                ])
        print(f"  🧾 Manifesto CSV:      {manifest_file}")
    except OSError as e:  # disco cheio, permissão, etc. — não aborta a execução
        print(f"  ⚠️  Não foi possível salvar o manifesto CSV: {e}")

    # [v7] Calculado ANTES do relatório, para a lista de hosts bloqueados
    # entrar no HTML (o aviso de stdout no fim usa as mesmas variáveis).
    real_blocks = _blocked_hosts - _api_unavailable

    # ---- [v5] Diagnóstico e relatório HTML ----
    if generate_report and failed_entries:
        print(f"\n{'=' * 70}")
        print(f"  🔍 DIAGNÓSTICO ({len(failed_entries)} artigos não baixados)")
        print(f"{'=' * 70}")
        if config.probe_failures:
            print(f"  Classificando falhas (~1 req por artigo)...\n")
        else:
            print(f"  Classificando falhas pelo motivo registrado (--no-probe)...\n")

        failed_items: list[dict] = []
        for idx, (entry, final_url, reason) in enumerate(failed_entries, 1):
            key = entry.get("ID", "?")
            doi = clean_doi(entry.get("doi", "")) if entry.get("doi") else ""
            print(f"  [{idx:3d}/{len(failed_entries)}] {key[:40]:<40s}", end=" ", flush=True)

            classification = classify_failure(
                doi, final_url, reason,
                probe=config.probe_failures,  # [v7]
            )

            # Enriquecer com metadados da entrada
            classification["key"] = key
            classification["doi"] = doi
            raw_title = entry.get("title", "Sem título")
            classification["title"] = raw_title.replace("{", "").replace("}", "")
            # [v8] sobrenome via splitname (era heurística manual de vírgula)
            classification["authors"] = _first_author_surname(
                entry.get("author", ""))
            classification["year"] = entry.get("year", "")
            classification["reason"] = reason

            failed_items.append(classification)
            print(f"→ {classification['label']}")
            if config.probe_failures:  # [v7] sem sondagem, sem pausa
                time.sleep(0.5)

        # Gerar HTML
        report_path = pdf_dir / "relatorio.html"
        generate_html_report(
            failed_items=failed_items,
            output_path=report_path,
            bib_path=bib_input,
            total_entries=total,
            downloaded=stats["baixado"],
            elapsed=elapsed,
            blocked_hosts=real_blocks,          # [v7]
            api_unavailable=_api_unavailable,   # [v7]
        )
        print(f"\n  📊 Relatório HTML salvo: {report_path}")
        print(f"     Abra no navegador para ver os links de download manual.")

    # [v6] Aviso sobre hosts que bloquearam durante a execução
    # ([v7] real_blocks calculado lá em cima, antes do relatório)
    if real_blocks:
        print(f"\n{'=' * 70}")
        print(f"  ⛔ HOSTS QUE BLOQUEARAM ({len(real_blocks)})")
        print(f"{'=' * 70}")
        for h in sorted(real_blocks):
            print(f"     {h}")
        print("\n     Desativados assim que responderam 429/403, para não agravar")
        print("     o bloqueio. Espere algumas horas antes de rodar de novo e baixe")
        print("     esses via navegador ou CAPES/CAFe.")

    if _api_unavailable:
        print(f"\n  ⓘ  APIs indisponíveis nesta execução ({len(_api_unavailable)}):")
        for h in sorted(_api_unavailable):
            print(f"     {h}")
        print("     Cota anônima esgotada ou chave necessária — não é bloqueio")
        print("     do seu IP. Costuma normalizar sozinho.")

    missing_count = stats["nao_encontrado"] + stats["sem_doi"] + stats["erro"]
    if missing_count > 0:
        print(f"\n  💡 {missing_count} artigo(s) não baixado(s).")
        if generate_report and failed_entries:
            print(f"     Relatório: {pdf_dir / 'relatorio.html'}")
        print(f"     Log:       {log_file}")
        print("     Baixe via CAPES/CAFe → https://periodicos.capes.gov.br")

    print("\n  ✅ Concluído!")


if __name__ == "__main__":
    main()
