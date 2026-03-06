import json

from functools import lru_cache
from pathlib import Path
from unittest import TestCase, mock

import requests

from configuracoes import FLARESOLVERR_HOST
from antigate import TurnstileSolverClient, FalhaSolucaoTurnstileException
from models import SolucaoAntigate


@lru_cache()
def obter_fixture(path: str) -> dict:
    p = Path('src/testes/fixtures').joinpath(path)
    with p.open('rb') as f:
        conteudo_fixture: bytes = f.read()
    return json.loads(conteudo_fixture)


class TestTurnstileSolverClient(TestCase):
    def setUp(self):
        self.url_pagina_captcha = 'https://tribunal.com.br'
        self.timeout = 60
        self.resolvedor = TurnstileSolverClient(
            url_pagina_captcha=self.url_pagina_captcha,
            timeout=self.timeout
        )

        self.mock_response = mock.create_autospec(spec=requests.Response, instance=True, **{'ok': True})
        self.mock_post = mock.create_autospec(spec=requests.post, **{'return_value': self.mock_response})
        return super().setUp()

    def test_resolver__realiza_requisicao_post_ao_servico_flaresolverr(self):
        """Deve realizar uma requisição POST ao endpoint do serviço do FlareSolverr com a payload esperada."""
        self.mock_response.json.return_value = obter_fixture('solucao_turnstile_sucesso.json')

        with mock.patch('antigate.requests.post', new=self.mock_post):
            self.resolvedor.resolver()

        self.mock_post.assert_called_once_with(
            url=f'{FLARESOLVERR_HOST}/v1',
            headers={'Content-Type': 'application/json'},
            json={
                'cmd': 'request.get',
                'url': self.url_pagina_captcha,
                'maxTimeout': 60000,
                'returnOnlyCookies': True
            }
        )

    def test_resolver__quando_proxy_estiver_configurado_deve_inlcuir_na_paylodad_de_acesso_ao_flaresolverr(self):
        """Quando o Proxy estiver configurado deve inlcluí-lo na payload."""
        self.mock_response.json.return_value = obter_fixture('solucao_turnstile_sucesso.json')

        with mock.patch('antigate.requests.post', new=self.mock_post), \
             mock.patch('antigate.os.environ', new={'HTTPS_PROXY': 'http://proxy.url:3128'}):
            self.resolvedor.resolver()

        self.mock_post.assert_called_once_with(
            url=f'{FLARESOLVERR_HOST}/v1',
            headers={'Content-Type': 'application/json'},
            json={
                'cmd': 'request.get',
                'url': self.url_pagina_captcha,
                'maxTimeout': 60000,
                'returnOnlyCookies': True,
                'proxy': {'url': 'http://proxy.url:3128'}
            }
        )

    def test_resolver__quando_sucesso_ao_solucionar_captcha_retorna_objeto_com_dados_da_sessao(self):
        """Deve retornar uma instância da classe ```models.SolucaoAntigate``` com os dados da sessão
        de acesso ao recurso do tribunal."""
        self.mock_response.json.return_value = obter_fixture('solucao_turnstile_sucesso.json')
        timestamp_fixo = 0

        with mock.patch('antigate.requests.post', new=self.mock_post), \
             mock.patch('antigate.time', return_value=timestamp_fixo):
            sessao_retornada = self.resolvedor.resolver()

        self.assertIsInstance(sessao_retornada, SolucaoAntigate)
        self.assertEqual(
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
            sessao_retornada.user_agent
        )
        self.assertEqual(
            'JSESSIONID=7pxKEj9M3NwlVpnVOhx3vqSVJIesd_9K5rqEJtjB.svlp-jboss-04; '
            'TS01528471=016a5b383380d13f34d73081ce32880e214f3a9203f2761333f422c671044a0351c20849f36ca3a0103d9'
            '55cb34f46983d0a7553dc; '
            'TS01e0d983=016a5b383380d13f34d73081ce32880e214f3a9203f2761333f422c671044a0351c20849f36ca3a0103d9'
            '55cb34f46983d0a7553dc; '
            'TS5d516d15027=0845fc7f4bab200035557f6b0dd3a79b73601662a98d4bfa56515cb18739e2463f2d29c09eb9e05d08'
            '0c42c4f4113000dea7232fe678c6ac0b090c19f999c4933aed94d2e6bb2ffce1e9c91e29565cf5b98603a40d38d47005'
            'f67d4d02955e79; '
            '_ga=GA1.1.443706025.1772327591; '
            '_ga_F31N0L6Z6D=GS2.1.s1772327591$o1$g0$t1772327591$j60$l0$h0; '
            '_gat_UA-179972319-1=1; '
            '_gid=GA1.3.964211319.1772327591; '
            '_hjSessionUser_3545185=eyJpZCI6IjQyZTcwNzdiLTIyYWMtNWNlNi1hNTliLTQxOTFkY2ZiYjIwZCIsImNyZWF0ZWQiO'
            'jE3NzIzMjc1OTE2NDgsImV4aXN0aW5nIjpmYWxzZX0=; '
            '_hjSession_3545185=eyJpZCI6ImViYTM2MzkyLTc2MzYtNGQzZC1hMzdlLTVjZDhkMzgyNzJmMSIsImMiOjE3NzIzMjc1O'
            'TE2NTAsInMiOjAsInIiOjAsInNiIjowLCJzciI6MCwic2UiOjAsImZzIjoxLCJzcCI6MH0=; '
            'cf_clearance=Ei4wyGOL36OUs04A7RJIboKWJJO43yRODyHuXPBbWY0-1772327591-1.2.1.1-yz_39hbpU6NhqB_n9fQi'
            'QAwol4AGK4zjG6SbHlfjzemgTiuyA5_Z6qiR74NJWLmXbMC1pYcrJOQXOjiJ03efp5HEDn.wsX2SBYQsw.kr4jnFrsAgtoG5'
            'Zn2JCBTvF3_GiltR5AHe0uzbu3ZX6xfJQXTmVZf5M6hfJoVZM0MMDfmBs5UFAv3a7P00GQhfWpGWKmanEzUpDtHmkf4g93v.'
            's5VJhZ_UMeWqV3iEaBvrBQLdLj5uu8WHglXCOhLyBuax; '
            'rpCookieInsert=4026535434.36895.0000',
            sessao_retornada.cookies
        )
        self.assertEqual(1800, sessao_retornada.tempo_de_vida)

    def test_resolver__quando_captcha_nao_encontrado_lanca_excecao(self):
        """Quando o FlareSolverr não encontrar o CAPTCHA na url informada, deve lançar
        FalhaSolucaoTurnstileException com a mensagem de erro do campo ```message``` do JSON da resposta."""
        self.mock_response.json.return_value = obter_fixture('solucao_turnstile_desafio_nao_detectado.json')

        with mock.patch('antigate.requests.post', new=self.mock_post), \
             self.assertRaisesRegex(FalhaSolucaoTurnstileException, 'Challenge not detected!'):
            self.resolvedor.resolver()

    def test_resolver__quando_ocorre_falha_ao_soluconar_captcha_lanca_excecao(self):
        """Quando o FlareSolverr retornar erro ao realizar a solução de captcha, deve lançar
        FalhaSolucaoTurnstileException com a mensagem de erro do campo ```message``` do JSON da resposta."""
        self.mock_response.json.return_value = obter_fixture('solucao_turnstile_erro_ao_solucionar.json')
        self.mock_response.ok = False
        mensagem_erro = 'Error: Error solving the challenge. Timeout after 0.12 seconds.'

        with mock.patch('antigate.requests.post', new=self.mock_post), \
             self.assertRaisesRegex(FalhaSolucaoTurnstileException, mensagem_erro):
            self.resolvedor.resolver()

    def test_resolver__quando_ocorre_falha_ao_processar_pedido_de_solucao_lanca_excecao(self):
        """Quando o FlareSolverr retornar erro ao procesar pedido de solução de captcha, deve lançar
        FalhaSolucaoTurnstileException com a mensagem de erro do campo ```error``` do JSON da resposta."""
        self.mock_response.json.return_value = obter_fixture('solucao_turnstile_erro_ao_processar_pedido.json')
        self.mock_response.ok = False

        with mock.patch('antigate.requests.post', new=self.mock_post), \
             self.assertRaisesRegex(FalhaSolucaoTurnstileException, "(400, 'Invalid JSON')"):
            self.resolvedor.resolver()

    def test_resolver__quando_ocorre_falha_ao_serializar_json_da_resposta_lanca_excecao_com_texto_da_resposta(self):
        """Quando não for possivel serializar o JSON da resposta do FlareSolverr, deve lançar
        FalhaSolucaoTurnstileException com o status code e texto da resposta."""
        self.mock_response.json.side_effect = requests.exceptions.JSONDecodeError('fake msg', 'fake doc', 0)
        self.mock_response.text = texto_resposta = 'Algum erro ocorrido!'
        self.mock_response.status_code = status_code_resposta = 500
        self.mock_response.ok = False

        with mock.patch('antigate.requests.post', new=self.mock_post), \
             self.assertRaisesRegex(FalhaSolucaoTurnstileException, f'({status_code_resposta}, "{texto_resposta}")'):
            self.resolvedor.resolver()
