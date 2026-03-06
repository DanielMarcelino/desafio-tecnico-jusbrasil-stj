import json
from functools import lru_cache
from pathlib import Path
from unittest import TestCase, mock

import requests
from tenacity import stop_after_attempt

from crawler_documento import CrawlerDocumento
from models import Documento
from storage import Storage


@lru_cache()
def obter_fixture(path: str) -> bytes:
    p = Path('src/testes/fixtures').joinpath(path)
    with p.open('rb') as f:
        conteudo_fixture: bytes = json.loads(f.read())
    return conteudo_fixture


class TesteCrawlerDocumentoEproc(TestCase):
    def setUp(self):
        self.mock_storage = mock.create_autospec(spec=Storage, instance=True)
        self.documento = Documento(
            identificador_unico='4134285346720240449175920250077440220251027',
            descricao='CERTIDÃO DE JULGAMENTO',
            link='/processo/julgamento/eletronico/documento/mediado/?documento_tipo=41'
            '&documento_sequencial=342853467&registro_numero=202404491759&peticao_numero=202500774402'
            '&publicacao_data=20251027',
            path_arquivo=None
        )
        self.crawler = CrawlerDocumento(
            storage=self.mock_storage, id_processo='202404491759',
            tipo_documento='anexos', documento=self.documento
        )
        # Desativar retry
        self.crawler._baixar_documento.retry.stop = stop_after_attempt(1)
        self.headers_resposta_arquivo = obter_fixture('headers_resposta_documento.json')
        self.headers_resposta_sem_arquivo = obter_fixture('headers_resposta_sem_documento.json')
        self.mock_response = mock.create_autospec(requests.Response, instance=True)
        return super().setUp()

    def test_possui_atributos(self):
        self.assertEqual(
            'https://processo.stj.jus.br/processo/pauta/buscar/?seq_documento={id_documento}',
            CrawlerDocumento.URL_BASE
        )
        self.assertDictEqual(
            {
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
            },
            CrawlerDocumento.HEADERS
        )
        self.assertEqual(60, CrawlerDocumento.TIMEOUT)

    def test_baixar_documento__quando_documento_nao_existe_no_storage__baixa_e_salva_arquivo(self):
        self.mock_response.headers = self.headers_resposta_arquivo
        self.mock_response.content = b'conteudo documento'
        self.mock_storage.existe.return_value = False

        with mock.patch.object(requests, 'get', return_value=self.mock_response) as mock_get:
            self.crawler.baixar_documento()

        # Verificou se o arquivo existe no storage
        self.mock_storage.existe.assert_called_once_with(
            path_arquivo='202404491759/anexos/4134285346720240449175920250077440220251027.*',
            wildcard=True
        )
        # Realizou requisicao
        mock_get.assert_called_once()
        # Documento recebeu o path do arquivo
        self.assertEqual(
            '202404491759/anexos/4134285346720240449175920250077440220251027.pdf',
            self.documento.path_arquivo
        )
        # Salvou arquivo no storage
        self.mock_storage.salvar_arquivo.assert_called_once_with(
            path_arquivo='202404491759/anexos/4134285346720240449175920250077440220251027.pdf',
            content=b'conteudo documento'
        )

    def test_baixar_documento__quando_documento_existe_no_storage__ignora_o_download(self):
        self.mock_storage.existe.return_value = True

        with mock.patch.object(requests, 'get', return_value=self.mock_response) as mock_get:
            self.crawler.baixar_documento()

        # Verificou se o arquivo existe no storage
        self.mock_storage.existe.assert_called_once_with(
            path_arquivo='202404491759/anexos/4134285346720240449175920250077440220251027.*',
            wildcard=True
        )
        # Não realizou requisição
        mock_get.assert_not_called()
        # Não salvou arquivo no storage
        self.mock_storage.salvar_arquivo.assert_not_called()

    def test_baixar_documento__quando_resposta_da_requisicao_nao_possui_documento__lanca_ValueError(self):
        self.mock_response.headers = self.headers_resposta_sem_arquivo
        self.mock_storage.existe.return_value = False

        with mock.patch.object(requests, 'get', return_value=self.mock_response):
            with self.assertRaises(ValueError):
                self.crawler.baixar_documento()

    def test_baixar_documento__quando_requisicao_mau_sucedida__executa_raise_for_status_lancando_excecao(self):
        self.mock_response.headers = self.headers_resposta_sem_arquivo
        self.mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError
        self.mock_storage.existe.return_value = False

        with mock.patch.object(requests, 'get', return_value=self.mock_response):
            with self.assertRaises(requests.exceptions.HTTPError):
                self.crawler.baixar_documento()

    def test_baixar_documento__quando_nao_extrair_id_documento_do_seu_link__lanca_excecao(self):
        self.mock_response.headers = self.headers_resposta_arquivo
        self.mock_response.content = b'conteudo documento'
        self.mock_storage.existe.return_value = False
        self.documento.link = 'link-insperado/123456789/'

        with mock.patch.object(requests, 'get', return_value=self.mock_response):
            with self.assertRaises(Exception):
                self.crawler.baixar_documento()

    def test_baixar_documento__realiza_requisicao_com_parametros_corretos_para_cada_tipo_de_link(self):
        self.mock_response.headers = self.headers_resposta_arquivo
        self.mock_response.content = b'conteudo documento'
        self.mock_storage.existe.return_value = False

        links = (
            '/processo/pauta/buscar/?seq_documento=320184034',
            (
                '/processo/dj/documento/mediado/?tipo_documento=documento&componente=MON&sequencial=320184034'
                '&tipo_documento=documento&num_registro=202404491759&data=20260112&tipo=0'
            ),
            (
                '/processo/julgamento/eletronico/documento/mediado/?documento_tipo=5'
                '&documento_sequencial=320184034&registro_numero=202404491759'
                '&peticao_numero=202500774402&publicacao_data=20251027'
            ),
        )
        for link in links:
            with self.subTest(link=link):
                self.documento.link = link
                with mock.patch.object(requests, 'get', return_value=self.mock_response) as mock_get:
                    self.crawler.baixar_documento()

                mock_get.assert_called_once_with(
                    url=self.crawler.URL_BASE.format(id_documento='320184034'),
                    headers=self.crawler.HEADERS,
                    timeout=self.crawler.TIMEOUT
                )
