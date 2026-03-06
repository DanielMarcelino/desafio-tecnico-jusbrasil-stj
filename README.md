# Crawler STJ

Crawler para extração automatizada de dados de processos judiciais do [Superior Tribunal de Justiça (STJ)](https://processo.stj.jus.br/processo/pesquisa/). O projeto realiza a busca, parsing, persistência e download de documentos de processos, com suporte a paginação, resolução de captcha e download assíncrono de arquivos.

Este projeto foi desenvolvido como solução para o desafio técnico do Jusbrasil.

---

## Requisitos

- **Python 3.12+** - o projeto utiliza recursos introduzidos no Python 3.12, como `zoneinfo` nativo e anotações de tipo modernas
- **Docker** - necessário para executar o FlareSolverr, responsável pela resolução do captcha Cloudflare Turnstile

---

## Instalação e execução

### 1. Instalar as dependências

```bash
pip install -r requirements/base.txt
```

### 2. Subir o FlareSolverr

O [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) deve estar em execução antes de iniciar o crawler, pois é responsável por resolver o captcha Cloudflare Turnstile do STJ:

```bash
docker run \
  -d \
  --name=flaresolverr \
  -p 8191:8191 \
  -e LOG_LEVEL=info \
  -e LANG="pt_BR" \
  -e "America/Sao_Paulo" \
  --restart unless-stopped \
  ghcr.io/flaresolverr/flaresolverr:latest

```

### 3. Executar o crawler

```bash
PYTHONPATH=src/ python src/run.py --processo "EAREsp 2814815"
```

O argumento `--processo` aceita qualquer um dos três formatos de número suportados (CNJ, número STJ ou registro STJ).

Ao fim da busca, os dados do processo e seus documentos estarão disponíveis no diretório `local_database/`, em uma pasta nomeada com o número de registro do processo no STJ. Os dados estarão representados em dois formatos: serializado em JSON e visual em HTML.

---

## Testes

Os testes unitários são executados via **tox** com relatório de cobertura:

```bash
tox -e coverage
```

Após a execução, o relatório de cobertura estará disponível em:

```
coverage/index.html
```

---

## Visão geral

O STJ utiliza proteção Cloudflare Turnstile para bloquear acesso automatizado. O crawler contorna essa proteção via [**FlareSolverr**](https://github.com/FlareSolverr/FlareSolverr), que resolve o desafio e fornece os cookies e User-Agent necessários para autenticar as requisições. A solução obtida é armazenada em cache no storage local e reutilizada entre execuções para evitar resoluções desnecessárias, sendo renovada automaticamente quando expirada ou quando a requisição retorna HTTP 403.

---

## Funcionalidades

- Busca de processos por três formatos de número
- Extração estruturada de detalhes, partes, advogados, petições, pautas e movimentos
- Suporte a paginação automática de movimentos
- Mesclagem e deduplicação de movimentos entre execuções
- Download assíncrono e paralelo de documentos
- Retry automático com backoff exponencial em falhas de rede
- Persistência local dos dados do processo em JSON e HTML
- Verificação de existência de arquivos com suporte a wildcard

---

## Formatos de número de processo aceitos

O crawler infere automaticamente o tipo do número via regex, sem necessidade de configuração adicional:

| Tipo | Formato | Exemplo |
|---|---|---|
| CNJ | `NNNNNNN-DD.AAAA.J.TT.OOOO` | `0001234-56.2023.1.00.0000` |
| Número STJ | `Classe NNNNNNN` | `REsp 1234567` |
| Registro STJ | `AAAA/NNNNNNN-D` | `2023/0123456-7` |

---

## Arquitetura

```
├── client_stj.py        # ClientSTJ — sessão HTTP, autenticação e paginação
├── crawler_processo.py  # CrawlerProcesso — orquestração do fluxo principal
├── crawler_documento.py # CrawlerDocumento — download individual de documentos
├── parser.py            # Parser — extração e parsing do HTML
├── models.py            # Modelos Pydantic (DadosProcesso, Processo, etc.)
├── storage.py           # Storage — persistência no sistema de arquivos local
├── antigate.py          # TurnstileSolverClient — integração com FlareSolverr
└── configuracoes.py     # Configurações globais
```

### Fluxo principal

```
CrawlerProcesso.buscar_processo()
        │
        ├── ClientSTJ                        # abre sessão autenticada
        │       ├── FlareSolverr             # resolve Turnstile → cookies + User-Agent
        │       ├── POST busca processo      # requisição principal
        │       └── POST páginas adicionais  # paginação de movimentos (se necessário)
        │
        ├── Parser                           # parsing do HTML → modelos Pydantic
        │
        ├── Processo.carregar()              # carrega registro local (se existir)
        ├── Processo.atualizar() / .criar()  # mescla ou cria novo registro
        │
        ├── CrawlerDocumento (paralelo)      # download assíncrono dos documentos
        │
        └── Processo.salvar()                # persiste JSON no storage local
```

---

## Estratégias de obtenção dos dados

### Autenticação via FlareSolverr

O STJ protege o portal com Cloudflare Turnstile. O `TurnstileSolverClient` delega a resolução do desafio ao [**FlareSolverr**](https://github.com/FlareSolverr/FlareSolverr), que retorna os cookies de sessão e o User-Agent necessários. Esses dados são injetados nos headers de todas as requisições via `requests.Session`.

A solução é armazenada no storage e reutilizada enquanto válida. Em caso de bloqueio (HTTP 403), o cliente descarta a solução em cache, obtém uma nova e repete a requisição automaticamente — sem intervenção manual.

### Parsing do HTML

O `Parser` utiliza **BeautifulSoup** com o parser `lxml` para extrair os dados do HTML retornado pelo STJ. Seletores CSS são usados para localizar os elementos estruturais, enquanto **regex** é aplicado para extração de valores dentro dos textos (números de processo, IDs de documentos, extensões de arquivo, datas). O método `_obter_soup` é memorizado por instância com `lru_cache`, evitando reparsing do mesmo HTML em chamadas consecutivas dentro de um mesmo fluxo de extração.

### Paginação de movimentos

O número total de movimentos é lido a partir de um campo hidden do formulário de paginação. O crawler calcula automaticamente a quantidade de páginas e requisita cada uma sequencialmente, acumulando os movimentos. A busca de páginas adicionais é otimizada: se o registro local já contempla todos os movimentos da página atual (verificado pela comparação de datas), as páginas restantes não são requisitadas.

### Download assíncrono de documentos

O download de documentos é realizado de forma **assíncrona** via `asyncio`, com execução paralela controlada por um `ThreadPoolExecutor` com limite definido por `MAX_CONEXOES_SIMULTANEAS`. Documentos de movimentos e de pautas são baixados simultaneamente. Cada download é executado em uma thread separada via `loop.run_in_executor`, permitindo que falhas individuais sejam capturadas e registradas em log sem interromper os demais downloads. A extensão do arquivo é desconhecida antes do download e é extraída do header `Content-Disposition` da resposta.

---

## Tratamento de erros e validações

### Retry com backoff exponencial

O download de documentos utiliza **Tenacity** com a seguinte configuração:

- Até **3 tentativas**
- Backoff exponencial entre **2 e 5 segundos**
- Retentar apenas em `requests.HTTPError` e `ValueError`
- Relança a exceção original após esgotamento das tentativas

O `ClientSTJ` implementa retry manual em caso de HTTP 403, forçando a renovação da sessão Turnstile antes da segunda tentativa.

### Validação de respostas

Antes de persistir o conteúdo de um documento, o crawler valida se a resposta contém o header `Content-Disposition` — indicando que a resposta é de fato um arquivo para download e não uma página de erro ou redirecionamento. Respostas sem esse header disparam `ValueError`, acionando o retry.

### Verificação de existência com wildcard

Como a extensão dos documentos só é conhecida após o download, a verificação de existência no storage usa **glob com wildcard** no nome do arquivo (ex: `0123456.*`), evitando downloads duplicados independente da extensão.

### Deduplicação de movimentos

Ao atualizar um processo existente, os movimentos são convertidos em `set` e mesclados via `union`. A igualdade e o hash de `Movimento` são calculados com base na `data` e `descricao`, garantindo que movimentos idênticos não sejam duplicados mesmo que apareçam em múltiplas execuções ou páginas.

### Modelos Pydantic

Todos os dados extraídos são validados por modelos **Pydantic**. Campos `datetime` são automaticamente normalizados para o fuso horário configurado em `TIME_ZONE` na entrada e serializados como ISO 8601 na saída JSON.

### Erros de parsing

O `Parser` lança `ValueError` com mensagens descritivas quando elementos HTML obrigatórios não são encontrados (labels, tags de valor, dados de pauta, dados de movimento). A exceção `NenhumRegistroEncontradoException` é lançada quando o HTML indica explicitamente que o processo não foi encontrado no sistema do STJ.

---

## Persistência

Os dados do processo são persistidos localmente em JSON, organizados por `id_processo` (dígitos do registro STJ):

```
local_storage/
└── {id_processo}/
    ├── dados_processo.html
    ├── dados_processo.json
    ├── anexos/
    │   └── {id_documento}.pdf
    └── pautas/
        └── {id_documento}.pdf
```


## Possíveis melhorias

### Resiliência e confiabilidade

- **Timeout nas requisições** — as chamadas `requests.get` e `session.request` não definem timeout explícito, o que pode causar travamentos indefinidos em caso de lentidão do servidor. Adicionar `timeout` como parâmetro configurável evitaria esse cenário.

### Manutenibilidade

- **Separar seletores CSS em constantes** — os seletores CSS estão dispersos nos métodos do `Parser`. Centralizá-los como constantes de classe facilitaria a atualização quando o layout do STJ mudar.

### Otimização

- **Refinar o enfileiramento de documentos para download** — atualmente todos os documentos do processo são enfileirados a cada execução, incluindo os que já foram baixados anteriormente. Eles não são baixados novamente pois a existência no storage é verificada antes do download, mas há um custo em realizar essa verificação para cada documento. A estratégia foi adotada intencionalmente para retentar documentos que sofreram falha em execuções anteriores. Uma melhoria possível seria rastrear quais documentos já foram baixados com sucesso e excluí-los da fila, mantendo apenas os pendentes ou com falha.


