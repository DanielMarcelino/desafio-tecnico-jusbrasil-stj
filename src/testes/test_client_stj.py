from types import GeneratorType
from unittest import TestCase, mock

import requests

from antigate import TurnstileSolverClient
from client_stj import ClientSTJ
from models import SolucaoAntigate, DadosProcesso, Movimento
from parser import Parser
from storage import Storage


def criar_solucao_antigate(ttl: int) -> SolucaoAntigate:
    return SolucaoAntigate(
        user_agent='Mozilla/5.0',
        cookies='cookie=123',
        tempo_de_vida=ttl
    )


PARAMETROS_BUSCA = {
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
PARAMETROS_PAGINACAO = {
    **PARAMETROS_BUSCA,
    'fasesNumPaginaAtual': 1,
    'fasesNumTotalRegistros': 0,
    'fasesVaiParaPaginaAnterior': 'false',
    'fasesVaiParaPaginaSeguinte': 'true',
    'fasesComProximaPagina': 'true'
}


class TestClientSTJ(TestCase):
    def setUp(self):
        self.resolvedor_turnstile = mock.create_autospec(spec=TurnstileSolverClient, instance=False)
        self.mock_storage = mock.create_autospec(spec=Storage, instance=True)
        self.mock_solucao_antigate = mock.create_autospec(spec=SolucaoAntigate, instance=True)
        self.mock_parser = mock.create_autospec(spec=Parser, instance=True)
        self.cliente_stj = ClientSTJ(
            storage=self.mock_storage,
            numero_processo='0000000-00.0000.0.00.0000'
        )
        self.cliente_stj._parser = self.mock_parser
        return super().setUp()

    def test_classe__possui_atributos(self):
        self.assertEqual('https://processo.stj.jus.br/processo/pesquisa/', ClientSTJ.URL_BASE)
        self.assertDictEqual(
            {
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
            },
            ClientSTJ.HEADERS_BASE
        )

    # Testes _recuperar_solucao_turnstile
    def test_recuperar_solucao_turnstile__obtem_solucao_do_storage_e_retorna(self):
        timestamp_fixo = 1000
        solucao_armazenada = criar_solucao_antigate(ttl=timestamp_fixo + 1)
        self.mock_solucao_antigate.obter_do_storage.return_value = solucao_armazenada

        with mock.patch('client_stj.SolucaoAntigate', new=self.mock_solucao_antigate), \
             mock.patch('models.time', return_value=timestamp_fixo):
            solucao_recuperada = self.cliente_stj._recuperar_solucao_turnstile()

        self.mock_solucao_antigate.obter_do_storage.assert_called_once_with(self.mock_storage)
        self.assertIsInstance(solucao_recuperada, SolucaoAntigate)
        self.assertDictEqual(solucao_armazenada.model_dump(), solucao_recuperada.model_dump())

    def test_recuperar_solucao_turnstile__quando_solucao_armazenada_expirada_retorna_none(self):
        timestamp_fixo = 1000
        solucao_armazenada = criar_solucao_antigate(ttl=timestamp_fixo - 1)
        self.mock_solucao_antigate.obter_do_storage.return_value = solucao_armazenada

        with mock.patch('client_stj.SolucaoAntigate', new=self.mock_solucao_antigate), \
             mock.patch('models.time', return_value=timestamp_fixo):
            solucao_recuperada = self.cliente_stj._recuperar_solucao_turnstile()

        self.mock_solucao_antigate.obter_do_storage.assert_called_once_with(self.mock_storage)
        self.assertIsNone(solucao_recuperada)

    def test_recuperar_solucao_turnstile__quando_nao_ha_solucao_armazenada_retorna_none(self):
        self.mock_solucao_antigate.obter_do_storage.return_value = None

        with mock.patch('client_stj.SolucaoAntigate', new=self.mock_solucao_antigate):
            solucao_recuperada = self.cliente_stj._recuperar_solucao_turnstile()

        self.mock_solucao_antigate.obter_do_storage.assert_called_once_with(self.mock_storage)
        self.assertIsNone(solucao_recuperada)

    # Testes _obter_nova_solucao_turnstile
    def test_obter_nova_solucao_turnstile__obtem_solucao_do_resolvedor_e_retorna(self):
        nova_solucao = criar_solucao_antigate(ttl=1000)
        self.resolvedor_turnstile.return_value.resolver.return_value = nova_solucao

        with mock.patch('client_stj.TurnstileSolverClient', new=self.resolvedor_turnstile):
            solucao_retornda = self.cliente_stj._obter_nova_solucao_turnstile()

        self.resolvedor_turnstile.assert_called_once_with(
            url_pagina_captcha=self.cliente_stj.URL_BASE
        )
        self.resolvedor_turnstile.return_value.resolver.assert_called_once_with()
        self.assertIsInstance(solucao_retornda, SolucaoAntigate)
        self.assertDictEqual(nova_solucao.model_dump(), solucao_retornda.model_dump())

    # Testes _obter_solucao_turnstile
    def test_obter_solucao_turnstile__quado_forcar_nova_solucao_for_false__recupera_solucao_armazenada(self):
        solucao_armazenada = criar_solucao_antigate(ttl=1000)

        with mock.patch.object(ClientSTJ, '_recuperar_solucao_turnstile', return_value=solucao_armazenada):
            solucao_obtida = self.cliente_stj._obter_solucao_turnstile(forcar_nova_solucao=False)

        self.assertIsInstance(solucao_obtida, SolucaoAntigate)
        self.assertDictEqual(solucao_armazenada.model_dump(), solucao_obtida.model_dump())
        self.assertDictEqual(solucao_armazenada.model_dump(), self.cliente_stj._solucao_turnstile.model_dump())

    def test_obter_solucao_turnstile__quando_solucao_recuperada_nao_eh_valida__obtem_nova_solucao(self):
        solucao_armazenada = None
        nova_solucao = criar_solucao_antigate(ttl=1000)

        with mock.patch.object(ClientSTJ, '_recuperar_solucao_turnstile', return_value=solucao_armazenada), \
             mock.patch.object(ClientSTJ, '_obter_nova_solucao_turnstile', return_value=nova_solucao):
            solucao_obtida = self.cliente_stj._obter_solucao_turnstile(forcar_nova_solucao=False)

        self.assertIsInstance(solucao_obtida, SolucaoAntigate)
        nova_solucao_dump: dict = nova_solucao.model_dump()
        self.assertDictEqual(nova_solucao_dump, solucao_obtida.model_dump())
        self.assertDictEqual(nova_solucao_dump, self.cliente_stj._solucao_turnstile.model_dump())

    def test_obter_solucao_turnstile__quado_forcar_nova_solucao_for_true__obtem_nova_solucao(self):
        nova_solucao = criar_solucao_antigate(ttl=1000)

        with mock.patch.object(ClientSTJ, '_obter_nova_solucao_turnstile', return_value=nova_solucao):
            solucao_obtida = self.cliente_stj._obter_solucao_turnstile(forcar_nova_solucao=True)

        self.assertIsInstance(solucao_obtida, SolucaoAntigate)
        nova_solucao_dump: dict = nova_solucao.model_dump()
        self.assertDictEqual(nova_solucao_dump, solucao_obtida.model_dump())
        self.assertDictEqual(nova_solucao_dump, self.cliente_stj._solucao_turnstile.model_dump())

    # Testes _configurar_sessao
    def test_configurar_sessao__quado_forcar_nova_solucao_for_false__obtem_solucao_e_configura_sessao(self):
        solucao_turnstile = criar_solucao_antigate(ttl=1000)
        headers_esperados = self.cliente_stj.HEADERS_BASE.copy()
        headers_esperados.update({'User-Agent': solucao_turnstile.user_agent, 'Cookie': solucao_turnstile.cookies})

        with mock.patch.object(ClientSTJ, '_obter_solucao_turnstile', return_value=solucao_turnstile):
            sessao_configurada = self.cliente_stj._configurar_sessao(forcar_nova_solucao=False)

            self.cliente_stj._obter_solucao_turnstile.assert_called_once_with(forcar_nova_solucao=False)

        self.assertIsInstance(sessao_configurada, requests.Session)
        self.assertDictEqual(headers_esperados, dict(sessao_configurada.headers))

    def test_configurar_sessao__quado_forcar_nova_solucao_for_true__obtem_nova_solucao_e_configura_sessao(self):
        solucao_turnstile = criar_solucao_antigate(ttl=1000)
        headers_esperados = self.cliente_stj.HEADERS_BASE.copy()
        headers_esperados.update({'User-Agent': solucao_turnstile.user_agent, 'Cookie': solucao_turnstile.cookies})

        with mock.patch.object(ClientSTJ, '_obter_solucao_turnstile', return_value=solucao_turnstile):
            sessao_configurada = self.cliente_stj._configurar_sessao(forcar_nova_solucao=True)

            self.cliente_stj._obter_solucao_turnstile.assert_called_once_with(forcar_nova_solucao=True)

        self.assertIsInstance(sessao_configurada, requests.Session)
        self.assertDictEqual(headers_esperados, dict(sessao_configurada.headers))

    # Testes _obter_sessao
    def test_obter_sessao__quando_sessao_ja_existe__retorna_sessao_atual(self):
        sessao_atual = requests.Session()
        self.cliente_stj._requests_session = sessao_atual

        sessao_obtida = self.cliente_stj._obter_sessao(forcar_nova_solucao=False)

        self.assertIs(sessao_atual, sessao_obtida)
        self.assertIs(sessao_atual, self.cliente_stj._requests_session)

    def test_obter_sessao__quando_nao_ha_sessao__configura_nova_e_retorna(self):
        self.cliente_stj._requests_session = None
        nova_sessao = requests.Session()

        with mock.patch.object(ClientSTJ, '_configurar_sessao', return_value=nova_sessao):
            sessao_obtida = self.cliente_stj._obter_sessao(forcar_nova_solucao=False)

            self.cliente_stj._configurar_sessao.assert_called_once_with(forcar_nova_solucao=False)

        self.assertIs(nova_sessao, sessao_obtida)
        self.assertIs(nova_sessao, self.cliente_stj._requests_session)

    def test_obter_sessao__quado_forcar_nova_solucao_for_true__fecha_sessao_atual_configura_nova_e_retorna(self):
        mock_sessao_atual = mock.create_autospec(spec=requests.Session, instance=True)
        self.cliente_stj._requests_session = mock_sessao_atual
        nova_sessao = requests.Session()

        with mock.patch.object(ClientSTJ, '_configurar_sessao', return_value=nova_sessao):
            sessao_obtida = self.cliente_stj._obter_sessao(forcar_nova_solucao=True)

            self.cliente_stj._configurar_sessao.assert_called_once_with(forcar_nova_solucao=True)

        mock_sessao_atual.close.assert_called_once_with()
        self.assertIs(nova_sessao, sessao_obtida)
        self.assertIs(nova_sessao, self.cliente_stj._requests_session)

    # Testes _realizar_requisicao
    def test_realizar_requisicao__obtem_sessao_realiza_requisicao_com_parametros_esperados_e_retona_resposta(self):
        mock_response = mock.create_autospec(spec=requests.Response, instance=True, status_code=200)
        mock_sessao = mock.create_autospec(spec=requests.Session, instance=True)
        mock_sessao.request.return_value = mock_response

        with mock.patch.object(ClientSTJ, '_obter_sessao', return_value=mock_sessao):
            resposta_obtida = self.cliente_stj._realizar_requisicao(
                method='GET', url='https://url.com', data={'parametro': 'valor'}
            )

            self.cliente_stj._obter_sessao.assert_called_once_with(forcar_nova_solucao=False)

        mock_sessao.request.assert_called_once_with(
            method='GET', url='https://url.com', data={'parametro': 'valor'}
        )
        self.assertIs(mock_response, resposta_obtida)

    def test_realizar_requisicao__quando_status_403_realiza_nova_tentativa_forcando_nova_solucao(self):
        mock_resposta_403 = mock.create_autospec(spec=requests.Response, instance=True, status_code=403)
        mock_resposta_200 = mock.create_autospec(spec=requests.Response, instance=True, status_code=200)
        mock_sessao = mock.create_autospec(spec=requests.Session, instance=True)
        mock_sessao.request.side_effect = (mock_resposta_403, mock_resposta_200)

        with mock.patch.object(ClientSTJ, '_obter_sessao', return_value=mock_sessao):
            resposta_obtida = self.cliente_stj._realizar_requisicao(
                method='GET', url='https://url.com', data={'parametro': 'valor'}
            )

            self.assertEqual(
                [mock.call(forcar_nova_solucao=False), mock.call(forcar_nova_solucao=True)],
                self.cliente_stj._obter_sessao.call_args_list
            )

        self.assertEqual(
            [
                mock.call(method='GET', url='https://url.com', data={'parametro': 'valor'}),
                mock.call(method='GET', url='https://url.com', data={'parametro': 'valor'})
            ],
            mock_sessao.request.call_args_list
        )
        self.assertIs(mock_resposta_200, resposta_obtida)

    def test_realizar_requisicao__quando_resposta_nao_e_ok_lanca_excecao(self):
        mock_resposta_500 = mock.create_autospec(spec=requests.Response, instance=True, status_code=500)
        mock_resposta_500.raise_for_status.side_effect = requests.exceptions.HTTPError
        mock_sessao = mock.create_autospec(spec=requests.Session, instance=True)
        mock_sessao.request.return_value = mock_resposta_500

        with mock.patch.object(ClientSTJ, '_obter_sessao', return_value=mock_sessao):
            with self.assertRaises(requests.exceptions.HTTPError):
                self.cliente_stj._realizar_requisicao(
                    method='GET', url='https://url.com', data={'parametro': 'valor'}
                )

            self.cliente_stj._obter_sessao.assert_called_once_with(forcar_nova_solucao=False)

        mock_sessao.request.assert_called_once_with(
            method='GET', url='https://url.com', data={'parametro': 'valor'}
        )

    # Testes buscar_processo
    def test_buscar_processo__extrai_dados_com_parser_e_retorna(self):
        mock_response = mock.create_autospec(spec=requests.Response, instance=True, text='<html>')
        dados_processo = mock.create_autospec(spec=DadosProcesso, instance=True)
        self.cliente_stj._parser.extrair_dados_processo.return_value = dados_processo

        with mock.patch.object(ClientSTJ, '_realizar_requisicao', return_value=mock_response):
            dados_retornados = self.cliente_stj.buscar_processo()

        self.assertIs(dados_processo, dados_retornados)

    def test_buscar_processo__define_atribuntos_instancia(self):
        mock_response = mock.create_autospec(spec=requests.Response, instance=True, text='<html>')
        self.cliente_stj._parser.extrair_quantidade_total_movimentos.return_value = 123

        with mock.patch.object(ClientSTJ, '_realizar_requisicao', return_value=mock_response):
            self.cliente_stj.buscar_processo()

        self.assertEqual('<html>', self.cliente_stj._html_primeira_pagina)
        self.assertEqual(123, self.cliente_stj._total_movimentos)

    def test_buscar_processo__executa_realizar_requisicao_com_parametros_esperados_para_cada_num_processo(self):
        processos = {
            '0000000-00.0000.0.00.0000': 'numeroUnico',
            '00000000000000000000': 'numeroUnico',  # CNJ sem máscara
            'ABCde 0000000': 'num_processo',
            '0000/0000000-0': 'num_registro',
            '000000000000': 'num_registro',  # Número Registro STJ sem máscara
        }
        for processo, chave_parametro in processos.items():
            with self.subTest(numero_processo=processo):
                client = ClientSTJ(self.mock_storage, numero_processo=processo)
                client._parser = self.mock_parser

                with mock.patch.object(ClientSTJ, '_realizar_requisicao') as mock_realizar_requisicao:
                    client.buscar_processo()

                parametros_esperados = PARAMETROS_BUSCA.copy()
                parametros_esperados.update({chave_parametro: processo})

                mock_realizar_requisicao.assert_called_once_with(
                    method='POST',
                    url=ClientSTJ.URL_BASE,
                    data=parametros_esperados
                )

    # Testes buscar_paginas_movimentos
    def test_buscar_paginas_movimentos__retorna_gerador_de_listas_com_movimentos(self):
        self.cliente_stj._html_primeira_pagina = 'html'
        self.cliente_stj._total_movimentos = 150
        self.cliente_stj._parser.extrair_quantidade_paginas.return_value = 3
        movimentos_esperados = [mock.create_autospec(spec=Movimento, instance=True)]
        self.cliente_stj._parser.extrair_movimentos.return_value = movimentos_esperados

        with mock.patch.object(ClientSTJ, '_realizar_requisicao'):
            retorno_obtido = self.cliente_stj.buscar_paginas_movimentos()

            self.assertIsInstance(retorno_obtido, GeneratorType)
            self.assertEqual([movimentos_esperados] * 2, list(retorno_obtido))

    def test_buscar_paginas_movimentos__executa_realizar_requisicao_com_parametros_esperados_para_cada_processo(self):
        processos = {
            '0000000-00.0000.0.00.0000': 'numeroUnico',
            '00000000000000000000': 'numeroUnico',  # CNJ sem máscara
            'ABCde 0000000': 'num_processo',
            '0000/0000000-0': 'num_registro',
            '000000000000': 'num_registro',  # Número Registro STJ sem máscara
        }
        for processo, chave_parametro in processos.items():
            with self.subTest(numero_processo=processo):
                client = ClientSTJ(self.mock_storage, numero_processo=processo)
                client._parser = self.mock_parser
                client._parser.extrair_quantidade_paginas.return_value = 3
                client._total_movimentos = 250
                client._html_primeira_pagina = 'html'

                with mock.patch.object(ClientSTJ, '_realizar_requisicao') as mock_realizar_requisicao:
                    paginas = client.buscar_paginas_movimentos()
                    if not paginas:
                        self.fail('Não houve iteração entre as páginas de movimentações!')
                    for _ in paginas:
                        pass

                parametros_esperados_1 = PARAMETROS_PAGINACAO.copy()
                parametros_esperados_1.update({
                    chave_parametro: processo, 'fasesNumPaginaAtual': 1, 'fasesNumTotalRegistros': 250
                })
                parametros_esperados_2 = parametros_esperados_1.copy()
                parametros_esperados_2.update({'fasesNumPaginaAtual': 2})

                chamadas_esperadas = [
                    mock.call(method='POST', url=ClientSTJ.URL_BASE, data=parametros_esperados_1),
                    mock.call(method='POST', url=ClientSTJ.URL_BASE, data=parametros_esperados_2)
                ]
                self.assertEqual(chamadas_esperadas, mock_realizar_requisicao.call_args_list)

    # Testes movimentos_paginados
    def test_movimentos_paginados__retorna_true_se_quantidade_paginas_for_maior_que_1(self):
        self.cliente_stj._html_primeira_pagina = 'html'
        self.cliente_stj._parser.extrair_quantidade_paginas.return_value = 2
        self.assertTrue(self.cliente_stj.movimentos_paginados)

    def test_movimentos_paginados__retorna_false_se_quantidade_paginas_for_igual_1(self):
        self.cliente_stj._html_primeira_pagina = 'html'
        self.cliente_stj._parser.extrair_quantidade_paginas.return_value = 1
        self.assertFalse(self.cliente_stj.movimentos_paginados)

    def test_movimentos_paginados__retorna_false_se_quantidade_paginas_for_menor_que_1(self):
        self.cliente_stj._html_primeira_pagina = 'html'
        self.cliente_stj._parser.extrair_quantidade_paginas.return_value = 0
        self.assertFalse(self.cliente_stj.movimentos_paginados)

    # Testes gerenciador de contexto
    def test_gerenciador_de_contexto__ao_encerrar_contexto__persiste_solucao_antigate_e_fecha_sessao(self):
        with ClientSTJ(storage=self.mock_storage, numero_processo='0000000-00.0000.0.00.0000') as client:
            client._solucao_turnstile = self.mock_solucao_antigate
            client._requests_session = mock.create_autospec(spec=requests.Session, instance=True)

        self.mock_solucao_antigate.persistir_no_storage.assert_called_once_with(storage=self.mock_storage)
        client._requests_session.close.assert_called_once_with()
