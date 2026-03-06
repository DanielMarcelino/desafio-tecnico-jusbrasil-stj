from datetime import datetime
from unittest import TestCase, mock

from client_stj import ClientSTJ
from crawler_processo import CrawlerProcesso
from models import DetalhesProcesso, DadosProcesso, Movimento, Pauta, Documento, Processo
from storage import Storage


def criar_movimentos(quantidade: int) -> list[Movimento]:
    return [Movimento.model_construct(data=datetime(2026, 1, n)) for n in range(1, quantidade + 1)]


def criar_dados() -> DadosProcesso:
    return DadosProcesso.model_construct(
        detalhes=DetalhesProcesso.model_construct(registro_stj='0000/0000000-0'),
        partes=[],
        advogados=[],
        peticoes=[],
        pautas=[],
        movimentos=[],
        ultima_atualizacao=datetime(2026, 1, 1)
    )


class TestCrawlerProcesso(TestCase):
    def setUp(self):
        self.mock_storage = mock.create_autospec(spec=Storage, instance=True)
        self.mock_client_stj = mock.create_autospec(spec=ClientSTJ, instance=False)
        self.mock_client_stj.return_value.__enter__.return_value = self.mock_client_stj
        self.crawler = CrawlerProcesso(storage=self.mock_storage, numero_processo='0000000-00.0000.0.00.0000')
        return super().setUp()

    def test_buscar_processo__cria_novo_processo_quando_nao_existe_no_storage(self):
        dados_processo_buscado = criar_dados()
        processo_carregado = None

        self.mock_client_stj.buscar_processo.return_value = dados_processo_buscado

        with mock.patch('crawler_processo.ClientSTJ', new=self.mock_client_stj), \
             mock.patch('crawler_processo.Processo.carregar', return_value=processo_carregado), \
             mock.patch('crawler_processo.Processo.criar') as mock_criar, \
             mock.patch('crawler_processo.Processo.salvar'):
            self.crawler.buscar_processo()

        mock_criar.asseert_called_once_with()

    def test_buscar_processo__atualiza_processo_quando_ja_esta_no_strage(self):
        dados_processo_buscado = criar_dados()
        processo_carregado = Processo(dados=dados_processo_buscado)

        self.mock_client_stj.buscar_processo.return_value = dados_processo_buscado

        with mock.patch('crawler_processo.ClientSTJ', new=self.mock_client_stj), \
             mock.patch('crawler_processo.Processo.carregar', return_value=processo_carregado), \
             mock.patch('crawler_processo.Processo.atualizar') as mock_atualizar, \
             mock.patch('crawler_processo.Processo.salvar'):
            self.crawler.buscar_processo()

        mock_atualizar.asseert_called_once_with(dados=dados_processo_buscado)

    def test_buscar_processo__retorna_id_processo_ao_final_da_busca(self):
        dados_processo_buscado = criar_dados()
        processo_carregado = Processo(dados=dados_processo_buscado)

        self.mock_client_stj.buscar_processo.return_value = dados_processo_buscado

        with mock.patch('crawler_processo.ClientSTJ', new=self.mock_client_stj), \
             mock.patch('crawler_processo.Processo.carregar', return_value=processo_carregado), \
             mock.patch('crawler_processo.Processo.atualizar'):
            id_processo = self.crawler.buscar_processo()

        self.assertEqual('000000000000', id_processo)

    def test_buscar_processo__busca_paginas_adicionais_quando_ha_paginacao_e_processo_desatualizado(self):
        processo_carregado = Processo(dados=criar_dados())

        dados_processo_buscado = criar_dados()
        movimentos_processo_buscado = [Movimento.model_construct(data=datetime(2026, 1, 2))]
        dados_processo_buscado.movimentos = movimentos_processo_buscado

        self.mock_client_stj.buscar_processo.return_value = dados_processo_buscado
        self.mock_client_stj.movimentos_paginados = True
        self.mock_client_stj.buscar_paginas_movimentos.return_value = (criar_movimentos(2) for i in range(0, 2))

        with mock.patch('crawler_processo.ClientSTJ', new=self.mock_client_stj), \
             mock.patch('crawler_processo.Processo.carregar', return_value=processo_carregado), \
             mock.patch('crawler_processo.Processo.atualizar'):
            self.crawler.buscar_processo()

        self.assertEqual(5, len(dados_processo_buscado.movimentos))

    def test_buscar_processo__nao_busca_paginas_adicionais_quando_ja_esta_atualizado(self):
        processo_carregado = Processo(dados=criar_dados())

        dados_processo_buscado = criar_dados()
        movimentos_processo_buscado = [Movimento.model_construct(data=datetime(2025, 12, 30))]
        dados_processo_buscado.movimentos = movimentos_processo_buscado

        self.mock_client_stj.buscar_processo.return_value = dados_processo_buscado
        self.mock_client_stj.movimentos_paginados = True

        with mock.patch('crawler_processo.ClientSTJ', new=self.mock_client_stj), \
             mock.patch('crawler_processo.Processo.carregar', return_value=processo_carregado), \
             mock.patch('crawler_processo.Processo.atualizar'):
            self.crawler.buscar_processo()

        self.mock_client_stj.buscar_paginas_movimentos.assert_not_called()

    def test_buscar_processo__salva_processo_no_storage_ao_final_da_busca(self):
        processo_carregado = Processo(dados=criar_dados())

        dados_processo_buscado = criar_dados()

        self.mock_client_stj.buscar_processo.return_value = dados_processo_buscado
        self.mock_client_stj.movimentos_paginados = False

        with mock.patch('crawler_processo.ClientSTJ', new=self.mock_client_stj), \
             mock.patch('crawler_processo.Processo.carregar', return_value=processo_carregado), \
             mock.patch('crawler_processo.Processo.atualizar'), \
             mock.patch('crawler_processo.Processo.salvar') as mock_salvar:
            self.crawler.buscar_processo()

        mock_salvar.assert_called_once_with(storage=self.mock_storage)

    def test_buscar_processo__executa_download_documentos(self):
        dados_processo_buscado = criar_dados()
        processo_carregado = Processo(dados=dados_processo_buscado)

        documento = Documento.model_construct(link='doc/link')
        dados_processo_buscado.movimentos = [
            Movimento.model_construct(data=datetime(2025, 12, 30), documentos=[documento])
        ]
        dados_processo_buscado.pautas = [Pauta.model_construct(documento=documento)]

        self.mock_client_stj.buscar_processo.return_value = dados_processo_buscado
        self.mock_client_stj.movimentos_paginados = False

        with mock.patch('crawler_processo.ClientSTJ', new=self.mock_client_stj), \
             mock.patch('crawler_processo.Processo.carregar', return_value=processo_carregado), \
             mock.patch('crawler_processo.Processo.atualizar'), \
             mock.patch('crawler_processo.CrawlerDocumento') as mock_crawler_documento:
            self.crawler.buscar_processo()

        self.assertEqual(
            [
                mock.call(
                    storage=self.mock_storage, id_processo='000000000000',
                    tipo_documento='anexos', documento=documento
                ),
                mock.call(
                    storage=self.mock_storage, id_processo='000000000000',
                    tipo_documento='pautas', documento=documento
                ),
            ],
            mock_crawler_documento.call_args_list
        )

        self.assertEqual(
            [mock.call(), mock.call()],
            mock_crawler_documento.return_value.baixar_documento.call_args_list
        )
