import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from itertools import chain

from client_stj import ClientSTJ
from configuracoes import MAX_CONEXOES_SIMULTANEAS
from crawler_documento import CrawlerDocumento
from models import Processo, DadosProcesso, Documento
from storage import Storage


class CrawlerProcesso:
    """Orquestra a busca, atualização e download de documentos de um processo do STJ.

    Coordena as operações de busca via `ClientSTJ`, persistência via `Processo`
    e download paralelo de documentos via `CrawlerDocumento`. O download dos
    documentos é executado de forma assíncrona com um pool de threads controlado
    por `MAX_CONEXOES_SIMULTANEAS`.

    A busca de páginas adicionais de movimentos só é realizada quando os
    movimentos estão paginados e o processo ainda não está atualizado —
    evitando requisições desnecessárias.

    Example:
        crawler = CrawlerProcesso(storage=storage, numero_processo='REsp 123')
        id_processo = crawler.buscar_processo()
    """
    def __init__(self, storage: Storage, numero_processo: str) -> None:
        """Inicializa o crawler com o storage e o número do processo.

        Args:
            storage: Instância de `Storage` usada para carregar e persistir
                o processo e seus documentos.
            numero_processo: Número do processo nos formatos CNJ, STJ ou
                registro STJ. Espaços nas extremidades são removidos.
        """
        self._storage = storage
        self._numero_processo = numero_processo.strip()
        self._logger = logging.getLogger(f"[{__name__}][{self.__class__.__name__}]")

    def buscar_processo(self) -> str:
        """Busca o processo no STJ, atualiza o registro local e baixa os documentos.

        O fluxo executado é:
        1. Busca os dados do processo via `ClientSTJ`
        2. Carrega o registro local existente do storage, se houver
        3. Busca páginas adicionais de movimentos se necessário
        4. Cria ou atualiza o `Processo` com os dados obtidos
        5. Baixa os documentos de movimentos e pautas de forma assíncrona
        6. Persiste o processo atualizado no storage

        Returns:
            Identificador numérico do processo (`id_processo`).
        """
        self._logger.info('Buscando dados processo número: %s', self._numero_processo)
        with ClientSTJ(storage=self._storage, numero_processo=self._numero_processo) as client:
            dados = client.buscar_processo()
            registro_stj = dados.detalhes.registro_stj

            processo: Processo | None = Processo.carregar(storage=self._storage, registro_stj=registro_stj)
            if client.movimentos_paginados and not self._processo_atualizado(processo, dados):
                for i, movimentos in enumerate(client.buscar_paginas_movimentos()):
                    self._logger.info('Buscando página adicional de movimentos. Página: %d', i)
                    dados.movimentos.extend(movimentos)

            if processo:
                processo.atualizar(dados=dados)
            else:
                processo = Processo.criar(dados=dados)

            asyncio.run(self._baixar_documentos_async(processo))

            processo.salvar(storage=self._storage)

        self._logger.info('Busca finalizada')

        return processo.id_processo

    def _processo_atualizado(self, processo: Processo | None, dados: DadosProcesso) -> bool:
        """Verifica se o registro local já contempla todos os movimentos recebidos.

        Considera o processo atualizado se não houver movimentos nos dados
        recebidos ou se a `ultima_atualizacao` do registro local for mais
        recente que a data do movimento mais antigo da página atual —
        indicando que os movimentos já foram processados anteriormente.

        Args:
            processo: Registro local do processo, ou `None` se não existir.
            dados: Dados recém-extraídos do STJ com os movimentos da página atual.

        Returns:
            `True` se o processo já estiver atualizado e a busca de páginas
            adicionais puder ser ignorada, `False` caso contrário.
        """
        if not dados.movimentos:
            return True
        if processo:
            data_movimento_mais_antigo = dados.movimentos[-1].data
            ultima_atualizacao = processo.dados.ultima_atualizacao
            if ultima_atualizacao > data_movimento_mais_antigo:
                return True
        return False

    async def _baixar_documentos_async(self, processo: Processo) -> None:
        """Baixa de forma assíncrona todos os documentos do processo.

        Agrega os documentos de movimentos (tipo `'anexos'`) e de pautas
        (tipo `'pautas'`) em uma lista de tasks e as executa em paralelo
        via `asyncio.gather`, usando um `ThreadPoolExecutor` com limite de
        conexões simultâneas definido por `MAX_CONEXOES_SIMULTANEAS`.

        Args:
            processo: Instância de `Processo` com os dados cujos documentos
                serão baixados.
        """
        self._logger.info('Enfileirando download de documentos')

        dados = processo.dados
        id_processo = processo.id_processo

        documentos_movimentos = chain.from_iterable(map(lambda m: m.documentos, dados.movimentos))
        tasks = [self._baixar_documento_async(id_processo, 'anexos', doc) for doc in documentos_movimentos]

        documentos_pautas = map(lambda p: p.documento, dados.pautas)
        tasks.extend([self._baixar_documento_async(id_processo, 'pautas', doc) for doc in documentos_pautas])

        if not tasks:
            self._logger.info('Não há documentos a serem enfileirados')

        executor = ThreadPoolExecutor(max_workers=MAX_CONEXOES_SIMULTANEAS)
        asyncio.get_running_loop().set_default_executor(executor)

        await asyncio.gather(*tasks)

    async def _baixar_documento_async(self, id_processo: str, tipo_documento: str, documento: Documento) -> None:
        """Baixa um único documento de forma assíncrona em uma thread do executor.

        Delega o download para `CrawlerDocumento.baixar_documento` executado
        via `loop.run_in_executor`, permitindo que operações bloqueantes de
        I/O não bloqueiem o loop de eventos. Erros são capturados e registrados
        no log sem interromper o download dos demais documentos.

        Args:
            id_processo: Identificador numérico do processo ao qual o documento
                pertence.
            tipo_documento: Categoria do documento — `'anexos'` para documentos
                de movimentos ou `'pautas'` para documentos de pautas.
            documento: Instância de `Documento` com os metadados do arquivo
                a ser baixado.
        """
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                executor=None,
                func=CrawlerDocumento(
                    storage=self._storage, id_processo=id_processo,
                    tipo_documento=tipo_documento, documento=documento
                ).baixar_documento
            )
        except Exception as e:
            self._logger.error(
                'Erro ao baixar documento %s identificador_unico=%d erro: %s',
                documento.descricao, documento.identificador_unico, str(e.args)
            )
