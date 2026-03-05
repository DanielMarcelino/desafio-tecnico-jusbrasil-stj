import re
import logging
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from models import Documento
from storage import Storage


RETRY_CONF: dict[str, Any] = {
    'stop': stop_after_attempt(3),  # quantidade de tentativas
    'wait': wait_exponential(multiplier=1, min=2, max=5),  # backoff exponencial
    'retry': retry_if_exception_type((requests.HTTPError, ValueError)),  # só retentar em HTTPError e ValueError
    'reraise': True  # relança a exceção original após esgotamento das tentativas
}


class CrawlerDocumento:
    """Realiza o download e persistência de documentos anexados a processos do STJ.

    Cada instância é responsável por um único documento. Antes de baixar,
    verifica se o arquivo já existe no storage usando wildcard no nome, pois
    a extensão do arquivo só é conhecida após a requisição, a partir do
    header `Content-Disposition` da resposta.

    O download é realizado com retry automático configurado em `RETRY_CONF`,
    com backoff exponencial em caso de `HTTPError` ou resposta inválida.

    Attributes:
        TEMPLATE_PATH_ARQUIVO: Template do caminho do arquivo no storage,
            parametrizado por `id_processo`, `tipo_documento` e `nome_arquivo`.
        URL_BASE: URL de download do documento, parametrizada pelo `id_documento`.
        HEADERS: Headers HTTP enviados em todas as requisições.

    Example:
        crawler = CrawlerDocumento(
            storage=storage,
            id_processo='0123456',
            tipo_documento='acordao',
            documento=documento
        )
        crawler.baixar_documento()
    """
    TEMPLATE_PATH_ARQUIVO = '{id_processo}/{tipo_documento}/{nome_arquivo}'

    URL_BASE = 'https://processo.stj.jus.br/processo/pauta/buscar/?seq_documento={id_documento}'

    HEADERS = {
        'Host': 'processo.stj.jus.br',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'X-Requested-With': 'XMLHttpRequest',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
        'TE': 'trailers'
    }

    def __init__(self, storage: Storage, id_processo: str, tipo_documento: str, documento: Documento):
        """Inicializa o crawler para um documento específico.

        Args:
            storage: Instância de `Storage` para verificação e persistência
                do arquivo.
            id_processo: Identificador numérico do processo ao qual o documento
                pertence. Usado na composição do caminho do arquivo.
            tipo_documento: Categoria do documento (ex: `'anexos'`, `'pautas'`).
                Usado na composição do caminho do arquivo.
            documento: Instância de `Documento` com os metadados do arquivo
                a ser baixado.
        """
        self._storage: Storage = storage
        self._id_processo: str = id_processo
        self._tipo_documento: str = tipo_documento
        self._documento: Documento = documento
        self._logger = logging.getLogger(f"[{__name__}][{self.__class__.__name__}]")

    def baixar_documento(self) -> None:
        """Baixa e persiste o documento no storage, se ainda não existir.

        Verifica previamente se já existe um arquivo com o identificador único
        do documento no storage (independente da extensão). Caso exista, o
        download é ignorado e um log informativo é emitido.

        Raises:
            requests.HTTPError: Se a requisição retornar erro HTTP após
                todas as tentativas de retry.
            ValueError: Se a resposta não contiver `Content-Disposition`
                válido após todas as tentativas de retry.
        """
        if self._existe():
            self._logger.info(
                'Documento %s id_unico=%s foi ignorado por já existir no local storage',
                self._documento.descricao or '',
                self._documento.identificador_unico
            )
            return
        self._logger.info('Baixando documento %s', self._documento.descricao)
        resposta = self._baixar_documento()
        self._salvar(resposta)

    @retry(**RETRY_CONF)
    def _baixar_documento(self) -> requests.Response:
        """Executa a requisição de download com retry automático.

        Requisita o arquivo e valida a resposta verificando a presença do
        header `Content-Disposition`. Em caso de resposta inválida, lança
        `ValueError` para acionar o retry.

        Returns:
            Objeto `requests.Response` com o conteúdo do arquivo.

        Raises:
            ValueError: Se a resposta não contiver `Content-Disposition` válido.
            requests.HTTPError: Se a requisição retornar status de erro.
        """
        resposta: requests.Response = self._requisitar_arquivo()
        if not self._resposta_valida(resposta):
            raise ValueError(f'Resposta inválida ao baixar documento link={self._documento.link}')
        return resposta

    def _requisitar_arquivo(self) -> requests.Response:
        """Monta a URL e realiza a requisição GET do arquivo.

        Extrai o ID do documento a partir do link e substitui na `URL_BASE`
        antes de realizar a requisição.

        Returns:
            Objeto `requests.Response` com a resposta da requisição.

        Raises:
            requests.HTTPError: Se a resposta retornar status de erro.
        """
        id = self._extrair_id_documento(self._documento.link)
        link = self.URL_BASE.format(id_documento=id)
        resposta = requests.get(url=link, headers=self.HEADERS)
        resposta.raise_for_status()
        return resposta

    def _resposta_valida(self, resposta: requests.Response) -> bool:
        """Verifica se a resposta contém o header `Content-Disposition`.

        A presença deste header indica que a resposta contém um arquivo
        para download e não uma página de erro ou redirecionamento.

        Args:
            resposta: Objeto `requests.Response` a ser validado.

        Returns:
            `True` se o header `Content-Disposition` estiver presente,
            `False` caso contrário.
        """
        if self._obter_content_dispotion(resposta):
            return True
        return False

    def _existe(self) -> bool:
        """Verifica se o documento já foi baixado e existe no storage.

        Usa wildcard na extensão do arquivo pois a extensão só é conhecida
        após o download, a partir do header `Content-Disposition`.

        Returns:
            `True` se já existir um arquivo correspondente no storage,
            `False` caso contrário.
        """
        nome_arquivo_com_wildcard = self._documento.identificador_unico + '.*'
        path_arquivo = self._obter_path_arquivo(nome_arquivo_com_wildcard)
        return self._storage.existe(path_arquivo=path_arquivo, wildcard=True)

    def _salvar(self, resposta: requests.Response) -> None:
        """Persiste o conteúdo da resposta no storage e atualiza o path do documento.

        Extrai a extensão do arquivo a partir do header `Content-Disposition`,
        compõe o nome e caminho do arquivo e salva o conteúdo binário no storage.
        Atualiza `documento.path_arquivo` com o caminho onde o arquivo foi salvo.

        Args:
            resposta: Objeto `requests.Response` com o conteúdo do arquivo
                e o header `Content-Disposition`.

        Raises:
            ValueError: Se não for possível extrair a extensão do arquivo
                a partir do header `Content-Disposition`.
        """
        extensao_arquivo = self._obter_extensao_arquivo(resposta)
        nome_arquivo = f'{self._documento.identificador_unico}.{extensao_arquivo}'
        path_arquivo = self._obter_path_arquivo(nome_arquivo)
        self._documento.path_arquivo = path_arquivo
        self._storage.salvar_arquivo(path_arquivo=path_arquivo, content=resposta.content)
        self._logger.info(
            'Documento %s baixado e salvo em %s', self._documento.descricao or '',
            self._storage._obter_path_completo(path_arquivo)
        )

    def _obter_extensao_arquivo(self, resposta: requests.Response) -> str:
        """Extrai a extensão do arquivo a partir do header `Content-Disposition`.

        Aplica regex no valor do header para localizar a extensão no padrão
        `filename=nome.ext`.

        Args:
            resposta: Objeto `requests.Response` com o header
                `Content-Disposition`.

        Returns:
            String com a extensão do arquivo em letras minúsculas (ex: `'pdf'`).

        Raises:
            ValueError: Se a extensão não puder ser extraída do header.
        """
        content_disposition = self._obter_content_dispotion(resposta) or ''
        match = re.search(r'filename=.+?\.([\w]{2,4})(?:;|\Z)', content_disposition)
        if not match:
            raise ValueError('Não foi possível obter a extensão do arquivo!')
        extensao = match.group(1)
        return extensao.lower()

    def _obter_content_dispotion(self, resposta: requests.Response) -> str | None:
        """Obtém o valor do header `Content-Disposition` da resposta.

        Tenta as variações de capitalização `Content-Disposition` e
        `content-disposition` para garantir compatibilidade com diferentes
        servidores.

        Args:
            resposta: Objeto `requests.Response` de onde o header será lido.

        Returns:
            Valor do header `Content-Disposition`, ou `None` se ausente.
        """
        chaves_headers = ('Content-Disposition', 'content-disposition')
        return next((v for c in chaves_headers if (v := resposta.headers.get(c))), None)

    def _extrair_id_documento(self, link: str) -> str:
        """Extrai o ID numérico do documento a partir do link.

        Suporta os padrões de query string `sequencial=`, `documento_sequencial=`
        e `seq_documento=`.

        Args:
            link: URL ou trecho de URL contendo o parâmetro com o ID do documento.

        Returns:
            String com o ID numérico do documento.

        Raises:
            Exception: Se nenhum padrão de ID for encontrado no link.
        """
        regex_padroes_ids = r'(?:(?:documento_)?sequencial|seq_documento)=(\d+)'
        if (match := re.search(regex_padroes_ids, link)):
            return match.group(1)
        raise Exception('Não foi possivel extrair o id do documento link=%s', link)

    def _obter_path_arquivo(self, nome_arquivo: str) -> str:
        """Compõe o caminho do arquivo no storage a partir do template.

        Args:
            nome_arquivo: Nome do arquivo incluindo extensão ou wildcard
                (ex: `'0001234.pdf'`, `'0001234.*'`).

        Returns:
            Caminho completo do arquivo no storage seguindo o padrão
            `id_processo/tipo_documento/nome_arquivo`.
        """
        return self.TEMPLATE_PATH_ARQUIVO.format(
            id_processo=self._id_processo,
            tipo_documento=self._tipo_documento,
            nome_arquivo=nome_arquivo
        )
