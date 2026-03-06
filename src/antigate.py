import os
import requests
from time import time

from configuracoes import FLARESOLVERR_HOST
from models import SolucaoAntigate


class FalhaSolucaoTurnstileException(Exception):
    """Lançada quando houver falha ao resolver o desafio do Cloudflare Turnstile.

    Pode ser disparada tanto por erros HTTP retornados pelo FlareSolverr
    quanto por mensagens de erro presentes no corpo da resposta JSON.
    """


class TurnstileSolverClient:
    """Cliente do FlareSolverr (https://github.com/FlareSolverr/FlareSolverr), resolvedor do
    CAPTCHA Cloudflare Turnstile.

    Encapsula a comunicação com o serviço FlareSolverr para obter cookies e
    user-agent válidos após a resolução automática do desafio Turnstile, retornando um objeto
    do tipo models.SolucaoAntigate com dados da sessão para uso nas requisições subsequentes.

    Attributes:
        URL_FLARESOLVER (str): Endpoint base da API do FlareSolverr, construído a
            partir da variável de configuração ``FLARESOLVERR_HOST``.
    """

    URL_FLARESOLVERR = f'{FLARESOLVERR_HOST}/v1'

    def __init__(self, url_pagina_captcha: str, timeout: int = 120) -> None:
        """Inicializa o cliente com a URL do desafio e o tempo limite da requisição.

        Args:
            url_pagina_captcha (str): URL da página protegida pelo Turnstile que
                o FlareSolverr deve acessar e resolver.
            timeout (int): Tempo máximo, em segundos, aguardado pelo FlareSolverr
                para resolver o desafio. Padrão: 120 segundos.
        """
        self._url_pagina_captcha = url_pagina_captcha
        self._timeout = timeout

    def resolver(self) -> SolucaoAntigate:
        """Envia a requisição ao FlareSolverr e retorna uma sessão autenticada.

        Monta o payload com o comando ``request.get``, incluindo proxy quando
        configurado, e delega a validação da resposta e a construção do modelo
        aos métodos auxiliares.

        Returns:
            SolucaoAntigate: Objeto de sessão contendo user-agent, cookies e tempo de
                vida extraídos da solução retornada pelo FlareSolverr.

        Raises:
            FalhaSolucaoTurnstileException: Se o FlareSolverr retornar status HTTP
                de erro ou uma mensagem de falha no corpo da resposta.
        """
        headers = {"Content-Type": "application/json"}
        data = {
            'cmd': 'request.get',
            'url': self._url_pagina_captcha,
            'maxTimeout': self._timeout * 1000,  # Transforma segundos em milissegundos
            'returnOnlyCookies': True
        }

        if https_proxy := os.environ.get('HTTPS_PROXY'):
            data.update({'proxy': {'url': https_proxy}})

        response = requests.post(url=self.URL_FLARESOLVERR, headers=headers, json=data)
        self._verificar_resposta(response)
        return self._criar_model_sessao(response)

    def _criar_model_sessao(self, response: requests.Response) -> SolucaoAntigate:
        """Constrói um ``models.SolucaoAntigate`` a partir da resposta bem-sucedida do FlareSolverr.

        Extrai o user-agent e os cookies da chave ``solution`` do JSON, serializa
        os cookies no formato ``nome=valor`` separados por ponto-e-vírgula e
        determina o menor TTL entre todos os cookies para definir o tempo de vida
        da solução.

        Args:
            response (requests.Response): Resposta HTTP bem-sucedida do FlareSolverr.

        Returns:
            SolucaoAntigate: Modelo de solução preenchido com user-agent, cookies serializados
                e o menor tempo de expiração encontrado entre os cookies.
        """
        json = response.json()
        user_agent = json['solution']['userAgent']
        cookies_map = map(lambda c: f'{c["name"]}={c["value"]}', json['solution']['cookies'])
        cookies_str = '; '.join(sorted(cookies_map))

        timestamp_atual = int(time())
        ttl = timestamp_atual + 1800  # 30 min

        return SolucaoAntigate(
            user_agent=user_agent,
            cookies=cookies_str,
            tempo_de_vida=ttl
        )

    def _verificar_resposta(self, response: requests.Response) -> None:
        """Verifica se a resposta do FlareSolverr indica sucesso; lança exceção caso contrário.

        Considera a resposta bem-sucedida somente quando o status HTTP é OK **e** o
        campo ``message`` do JSON é exatamente ``'Challenge solved!'``. Qualquer outro
        cenário - status de erro, mensagem diferente ou corpo não-JSON - resulta em
        uma exceção com a mensagem de erro mais específica disponível.

        A mensagem de erro é extraída priorizando o campo ``message``; caso esteja
        ausente ou vazio, utiliza o campo ``error``. Se o corpo da resposta não for
        JSON válido, o texto bruto é usado como mensagem da exceção.

        Args:
            response (requests.Response): Resposta HTTP retornada pelo FlareSolverr.

        Raises:
            FalhaSolucaoTurnstileException: Se o status HTTP não for OK, se o desafio
                não tiver sido resolvido com sucesso ou se o corpo não puder ser
                interpretado como JSON.
        """
        try:
            json = response.json()
            if not response.ok or json.get('message', '') != 'Challenge solved!':
                mensagem_erro = json.get('message', '') or json.get('error', '')
                raise FalhaSolucaoTurnstileException(mensagem_erro)
        except requests.exceptions.JSONDecodeError:
            raise FalhaSolucaoTurnstileException(f'({response.status_code}, "{response.text}")')
