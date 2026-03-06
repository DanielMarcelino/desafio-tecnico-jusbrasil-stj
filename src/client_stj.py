import re
import logging
from typing import Generator

import requests

from antigate import TurnstileSolverClient
from models import SolucaoAntigate, DadosProcesso, Movimento
from parser import Parser
from storage import Storage


class ClientSTJ:
    """Cliente HTTP para busca e extração de dados de processos no STJ.

    Gerencia a sessão HTTP, autenticação via solução do CAPTCHA Turnstile (antigate),
    paginação de movimentos e parsing do HTML retornado pelo sistema do STJ.

    Deve ser usado como context manager para garantir que a sessão HTTP e
    a solução do Turnstile sejam finalizadas corretamente ao término do uso.

    Attributes:
        URL_BASE: URL base do sistema de pesquisa processual do STJ.
        HEADERS_BASE: Headers HTTP padrão enviados em todas as requisições.
        TIMEOUT (int): Tempo máximo de espera em segundos pela resposta de uma
            requisição HTTP realizada ao STJ.

    Example:
        with ClientSTJ(storage=storage, numero_processo='REsp 1234567') as client:
            dados = client.buscar_processo()
            for movimentos in client.buscar_paginas_movimentos():
                dados.movimentos.extend(movimentos)
    """
    URL_BASE = 'https://processo.stj.jus.br/processo/pesquisa/'
    HEADERS_BASE = {
        'Host': 'processo.stj.jus.br',
        'User-Agent': '',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Referer': 'https://processo.stj.jus.br/processo/pesquisa/?aplicacao=processos',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://processo.stj.jus.br',
        'Connection': 'keep-alive',
        'Cookie': '',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Priority': 'u=0, i',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
    }
    TIMEOUT = 30

    def __init__(self, storage: Storage, numero_processo: str,) -> None:
        """Inicializa o cliente com o storage e o número do processo.

        Args:
            storage: Instância de `Storage` usada para persistir e recuperar
                a solução do Turnstile entre execuções.
            numero_processo: Número do processo nos formatos CNJ, STJ ou
                registro STJ. Espaços nas extremidades são removidos.
        """
        self._storage: Storage = storage
        self._numero_processo = numero_processo.strip()
        self._parser = Parser()
        self._html_primeira_pagina: str
        self._total_movimentos: int | None
        self._solucao_turnstile: SolucaoAntigate | None = None
        self._requests_session: requests.Session | None = None
        self._logger = logging.getLogger(f"[{__name__}][{self.__class__.__name__}]")

    def __enter__(self) -> 'ClientSTJ':
        """Retorna a própria instância ao entrar no context manager."""
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Persiste a solução do Turnstile no storage e fecha a sessão HTTP."""
        if self._solucao_turnstile:
            self._solucao_turnstile.persistir_no_storage(storage=self._storage)
            self._token_sessao = None
        if self._requests_session:
            self._requests_session.close()

    def buscar_processo(self) -> DadosProcesso:
        """Realiza a busca do processo no STJ e retorna os dados extraídos.

        Efetua uma requisição POST com os parâmetros do processo, armazena
        o HTML da primeira página e o total de movimentos para uso posterior
        na paginação.

        Returns:
            Objeto `DadosProcesso` com todos os dados extraídos da primeira página.

        Raises:
            requests.HTTPError: Se a resposta retornar status de erro após
                as tentativas de renovação da sessão.
        """
        parametros_busca = self._obter_parametros_busca_processo()
        resposta = self._realizar_requisicao(method='POST', url=self.URL_BASE, data=parametros_busca)
        self._html_primeira_pagina = resposta.text
        self._total_movimentos = self._parser.extrair_quantidade_total_movimentos(self._html_primeira_pagina)
        return self._parser.extrair_dados_processo(self._html_primeira_pagina)

    @property
    def movimentos_paginados(self) -> bool:
        """Indica se os movimentos do processo estão distribuídos em mais de uma página.

        Returns:
            `True` se houver mais de uma página de movimentos, `False` caso contrário.
        """
        return self._parser.extrair_quantidade_paginas(self._html_primeira_pagina) > 1

    def buscar_paginas_movimentos(self) -> Generator[list[Movimento], None, None]:
        """Itera sobre as páginas de movimentos a partir da segunda página.

        Não realiza nenhuma requisição se os movimentos couberem em uma única página.

        Yields:
            Lista de objetos `Movimento` extraídos de cada página adicional.

        Raises:
            requests.HTTPError: Se alguma requisição de paginação retornar erro.
        """
        quantidade_paginas = self._parser.extrair_quantidade_paginas(self._html_primeira_pagina)
        if not (quantidade_paginas > 1):
            return
        for pagina in range(2, quantidade_paginas + 1):
            parametros_paginacao = self._obter_parametros_proxima_pagina(num_pagina=pagina)
            resposta = self._realizar_requisicao(method='POST', url=self.URL_BASE, data=parametros_paginacao)
            yield self._parser.extrair_movimentos(resposta.text)

    def _realizar_requisicao(self, method: str, url: str, data: dict) -> requests.Response:
        """Executa uma requisição HTTP com retry automático em caso de status 403.

        Na primeira tentativa reutiliza a sessão e solução Turnstile existentes.
        Se a resposta for 403, força a obtenção de uma nova solução e tenta
        novamente antes de lançar o erro.

        Args:
            method: Método HTTP (ex: `'POST'`, `'GET'`).
            url: URL de destino da requisição.
            data: Dicionário de parâmetros enviados no corpo da requisição.

        Returns:
            Objeto `requests.Response` com a resposta bem-sucedida.

        Raises:
            requests.HTTPError: Se a resposta retornar erro mesmo após o retry.
        """
        for forcar_nova_solucao in (False, True):
            requests_session: requests.Session = self._obter_sessao(forcar_nova_solucao=forcar_nova_solucao)
            resposta = requests_session.request(method=method, url=url, data=data, timeout=self.TIMEOUT)
            if resposta.status_code != 403:
                break
        resposta.raise_for_status()
        return resposta

    def _obter_sessao(self, forcar_nova_solucao: bool) -> requests.Session:
        """Retorna a sessão HTTP ativa, criando uma nova se necessário.

        Reutiliza a sessão existente se `forcar_nova_solucao` for `False`.
        Caso contrário, fecha a sessão atual e cria uma nova com solução
        Turnstile renovada.

        Args:
            forcar_nova_solucao: Se `True`, descarta a sessão atual e obtém
                uma nova solução do Turnstile.

        Returns:
            Objeto `requests.Session` configurado e pronto para uso.
        """
        if self._requests_session and not forcar_nova_solucao:
            return self._requests_session
        if self._requests_session:
            self._requests_session.close()
        self._requests_session = self._configurar_sessao(forcar_nova_solucao=forcar_nova_solucao)
        return self._requests_session

    def _configurar_sessao(self, forcar_nova_solucao: bool) -> requests.Session:
        """Cria e configura uma nova sessão HTTP com headers e cookies do Turnstile.

        Combina os `HEADERS_BASE` com o `User-Agent` e `Cookie` obtidos da
        solução do Turnstile.

        Args:
            forcar_nova_solucao: Repassado para `_obter_solucao_turnstile` para
                controlar se uma nova solução deve ser obtida.

        Returns:
            Objeto `requests.Session` com headers configurados.
        """
        solucao_turntile = self._obter_solucao_turnstile(forcar_nova_solucao=forcar_nova_solucao)
        headers_solucao_turnstile = {
            'User-Agent': solucao_turntile.user_agent,
            'Cookie': solucao_turntile.cookies
        }

        # Monta Headers a partir do HEADERS_BASE
        headers_configurados = self.HEADERS_BASE.copy()
        headers_configurados.update(headers_solucao_turnstile)

        # Configura Headers na sessao
        requests_session = requests.Session()
        requests_session.headers.update(headers_configurados)

        return requests_session

    def _obter_solucao_turnstile(self, forcar_nova_solucao: bool) -> SolucaoAntigate:
        """Obtém a solução do Turnstile, recuperando do storage ou resolvendo novamente.

        Tenta recuperar uma solução válida e não expirada do storage. Se não
        houver solução disponível ou `forcar_nova_solucao` for `True`, resolve
        um novo desafio Turnstile.

        Args:
            forcar_nova_solucao: Se `True`, ignora a solução em cache e força
                a resolução de um novo desafio.

        Returns:
            Objeto `SolucaoAntigate` com user agent e cookies válidos.
        """
        self._solucao_turnstile = (
            not forcar_nova_solucao and self._recuperar_solucao_turnstile()
        ) or self._obter_nova_solucao_turnstile()
        return self._solucao_turnstile

    def _obter_nova_solucao_turnstile(self) -> SolucaoAntigate:
        """Resolve um novo desafio Turnstile via `TurnstileSolverClient`.

        Returns:
            Objeto `SolucaoAntigate` com a solução recém-obtida.
        """
        self._logger.info('Resolvendo CAPTCHA Cloudflare Turnstile')
        resolvedor_turnstile = TurnstileSolverClient(url_pagina_captcha=self.URL_BASE)
        return resolvedor_turnstile.resolver()

    def _recuperar_solucao_turnstile(self) -> SolucaoAntigate | None:
        """Tenta recuperar uma solução Turnstile válida do storage.

        Returns:
            Objeto `SolucaoAntigate` se existir uma solução não expirada,
            `None` caso contrário.
        """
        solucao_recuperada = SolucaoAntigate.obter_do_storage(self._storage)
        return solucao_recuperada if solucao_recuperada and not solucao_recuperada.expirou else None

    def _obter_parametros_proxima_pagina(self, num_pagina: int) -> dict:
        """Monta os parâmetros de paginação para requisitar uma página específica.

        Parte dos parâmetros base de busca e adiciona os campos de controle
        de paginação necessários para avançar para a página solicitada.

        Args:
            num_pagina: Número da página desejada (base 1, a partir da página 2).

        Returns:
            Dicionário de parâmetros prontos para envio no corpo da requisição.
        """
        parametros = self._obter_parametros_busca_processo()
        parametros.update({
            'fasesNumPaginaAtual': num_pagina - 1,
            'fasesNumTotalRegistros': self._total_movimentos,
            'fasesVaiParaPaginaAnterior': 'false',
            'fasesVaiParaPaginaSeguinte': 'true',
            'fasesComProximaPagina': 'true'
        })
        return parametros

    def _obter_parametros_busca_processo(self) -> dict:
        """Monta o dicionário de parâmetros para a requisição de busca do processo.

        Infere o tipo do número do processo (CNJ, STJ ou registro STJ) via regex
        e preenche o campo correspondente. Os demais parâmetros são fixos e
        refletem os filtros padrão da pesquisa processual.

        Returns:
            Dicionário de parâmetros prontos para envio no corpo da requisição.

        Raises:
            ValueError: Se o número do processo não corresponder a nenhum
                dos formatos suportados (CNJ, STJ ou registro STJ).
        """
        parametros = {
            'aplicacao': 'processos',
            'acao': 'pushconsultarprocessoconsultalimitenaoatendidasjaincluidas',
            'descemail': '',
            'senha': '',
            'totalRegistrosPorPagina': 40,
            'tipoPesquisaSecundaria': '',
            'sequenciaisParteAdvogado': -1,
            'refinamentoAdvogado': '',
            'refinamentoParte': '',
            'tipoOperacaoFonetica': '',
            'tipoOperacaoFoneticaPhonos': 2,
            'origemOrgaosSelecionados': '',
            'origemUFSelecionados': '',
            'julgadorOrgaoSelecionados': '',
            'tipoRamosDireitoSelecionados': '',
            'situacoesSelecionadas': '',
            'num_processo': '',
            'num_registro': '',
            'numeroUnico': '',
            'numeroOriginario': '',
            'advogadoCodigo': '',
            'dataAutuacaoInicial': '',
            'dataAutuacaoFinal': '',
            'pautaPublicacaoDataInicial': '',
            'pautaPublicacaoDataFinal': '',
            'dataPublicacaoInicial': '',
            'dataPublicacaoFinal': '',
            'parteAutor': 'false',
            'parteReu': 'false',
            'parteOutros': 'false',
            'parteNome': '',
            'opcoesFoneticaPhonosParte': 2,
            'quantidadeMinimaTermosPresentesParte': 1,
            'advogadoNome': '',
            'opcoesFoneticaPhonosAdvogado': 2,
            'quantidadeMinimaTermosPresentesAdvogado': 1,
            'conectivo': 'OU',
            'listarProcessosOrdemDescrecente': 'true',
            'listarProcessosOrdemDescrecenteTemp': 'true',
            'listarProcessosAtivosSomente': 'false',
            'listarProcessosEletronicosSomente': 'true'
        }

        if self._is_cnj(self._numero_processo):
            parametros['numeroUnico'] = self._numero_processo
        elif self._is_proc_stj(self._numero_processo):
            parametros['num_processo'] = self._numero_processo
        elif self._is_reg_stj(self._numero_processo):
            parametros['num_registro'] = self._numero_processo
        else:
            raise ValueError('Número de processo inesperado!')
        return parametros

    def _is_cnj(self, mumero_processo: str) -> bool:
        """Verifica se o número do processo está no formato CNJ.

        Args:
            mumero_processo: Número do processo a verificar.

        Returns:
            `True` se o número corresponder ao padrão CNJ, `False` caso contrário.
        """
        regex_cnj = r'\A\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}\Z'
        return bool(re.match(regex_cnj, mumero_processo))

    def _is_proc_stj(self, mumero_processo: str) -> bool:
        """Verifica se o número do processo está no formato do STJ (ex: `REsp 1234567`).

        Args:
            mumero_processo: Número do processo a verificar.

        Returns:
            `True` se o número corresponder ao padrão STJ, `False` caso contrário.
        """
        regex_numero_processo_stj = r'\A[A-z]+ *\d+\Z'
        return bool(re.match(regex_numero_processo_stj, mumero_processo))

    def _is_reg_stj(self, mumero_processo: str) -> bool:
        """Verifica se o número do processo está no formato de registro STJ
        (ex: `2023/0123456-7`).

        Args:
            mumero_processo: Número do processo a verificar.

        Returns:
            `True` se o número corresponder ao padrão de registro STJ,
            `False` caso contrário.
        """
        regex_registro_stj = r'\A\d{4}/?\d+-?\d+\Z'
        return bool(re.match(regex_registro_stj, mumero_processo))
