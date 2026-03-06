import re
from datetime import datetime
from functools import lru_cache
from typing import Generator

from bs4 import BeautifulSoup, Tag

from configuracoes import TIME_ZONE
from models import DadosProcesso, DetalhesProcesso, Parte, Advogado, Peticao, Pauta, Movimento, Documento


class NenhumRegistroEncontradoException(Exception):
    """Lançada quando a busca por processo não retorna nenhum registro."""


class Parser:
    """Extrai dados estruturados de processos judiciais a partir de HTML do STJ.

    Realiza o parsing do HTML retornado pelo sistema do STJ, extraindo e
    estruturando informações como detalhes do processo, partes, advogados,
    petições, pautas e movimentos.

    O método `_obter_soup` é automaticamente memorizado com `lru_cache`
    (maxsize=2) na instância, evitando reparsing do mesmo HTML em chamadas
    consecutivas dentro de `extrair_dados_processo`.

    Example:
        parser = Parser()
        dados = parser.extrair_dados_processo(html)
    """

    def __init__(self):
        # Aplica lru_cache na instância (não na classe) para que o cache seja
        # por instância e não compartilhado entre objetos distintos.
        setattr(self, self._obter_soup.__name__, lru_cache(maxsize=2)(self._obter_soup))

    def extrair_dados_processo(self, html: str) -> DadosProcesso:
        """Extrai todos os dados do processo a partir do HTML completo da página.

        Agrega detalhes, partes, advogados, petições, pautas e movimentos em
        um único objeto `DadosProcesso`. A `ultima_atualizacao` é preenchida
        com o momento atual no fuso horário configurado.

        Args:
            html: Conteúdo HTML da página do processos em str.

        Returns:
            Objeto `DadosProcesso` preenchido com todos os dados extraídos.
        """
        return DadosProcesso(
            detalhes=self.extrair_detalhes(html),
            partes=self.extrair_partes(html),
            advogados=self.extrair_advogados(html),
            peticoes=self.extrair_peticoes(html),
            pautas=self.extrair_pautas(html),
            movimentos=self.extrair_movimentos(html),
            ultima_atualizacao=datetime.now(TIME_ZONE)
        )

    def extrair_detalhes(self, html: str) -> DetalhesProcesso:
        """Extrai os metadados estruturais do processo a partir dos blocos de detalhes.

        Lê os três blocos de detalhes do HTML (dados gerais, relator/assuntos,
        origem) e mapeia cada label para seu valor correspondente.

        Args:
            html: Conteúdo HTML da página do processo em str.

        Returns:
            Objeto `DetalhesProcesso` com os metadados extraídos.

        Raises:
            NenhumRegistroEncontradoException: Se o HTML indicar que nenhum
                processo foi encontrado.
        """
        soup = self._obter_soup(html)
        self._verificar_existencia(soup)

        detalhes_bloco_1 = self._obter_detalhes(soup=soup, bloco=1)
        detalhes_bloco_2 = self._obter_detalhes(soup=soup, bloco=2)
        detalhes_bloco_3 = self._obter_detalhes(soup=soup, bloco=3)

        volume = self._remover_pontuacao(v) if (v := self._extrair_texto_tag(detalhes_bloco_3.get(''))) else None
        tipo = self._remover_pontuacao(t) if (t := self._extrair_texto_tag(detalhes_bloco_1.get('TIPO:'))) else None

        return DetalhesProcesso(
            numero_stj=self._extrair_numero_stj(soup),
            registro_stj=self._extrair_registro_stj(soup),
            numero_cnj=self._extrair_texto_tag(detalhes_bloco_1.get('NÚMERO ÚNICO:')),
            classe=self._extrair_texto_tag(detalhes_bloco_1.get('PROCESSO:')),
            localizacao=self._extrair_texto_tag(detalhes_bloco_1.get('LOCALIZAÇÃO:')),
            tipo=tipo,
            autuacao=self._extrair_date_tag(detalhes_bloco_1.get('AUTUAÇÃO:')),
            relator=self._extrair_texto_tag(detalhes_bloco_2.get('RELATOR(A):')),
            ramo_do_direito=self._extrair_texto_tag(detalhes_bloco_2.get('RAMO DO DIREITO:')),
            assuntos=self._extrair_assuntos(detalhes_bloco_2.get('ASSUNTO(S):')),
            tribunal_origem=self._extrair_texto_tag(detalhes_bloco_3.get('TRIBUNAL DE ORIGEM:')),
            volume_apenso=volume,
            numeros_de_origem=self._extrair_numeros_origem(detalhes_bloco_3.get('NÚMEROS DE ORIGEM:')),
        )

    def extrair_partes(self, html: str) -> list[Parte]:
        """Extrai as partes do processo, excluindo advogados.

        Itera sobre todas as entradas de partes/advogados do HTML e filtra
        apenas aquelas cuja designação não começa com 'Advogado'.

        Args:
            html: Conteúdo HTML da página do processo em str.

        Returns:
            Lista de objetos `Parte` com designação e nome.
        """
        partes: list[Parte] = []
        for designacao, nome in self._extrair_partes(html):
            if designacao.startswith('Advogado'):
                continue
            partes.append(Parte(designacao=designacao, nome=nome))
        return partes

    def extrair_advogados(self, html: str) -> list[Advogado]:
        """Extrai os advogados vinculados ao processo.

        Filtra as entradas cuja designação começa com 'Advogado' e separa
        nome e número de OAB usando regex no formato `Nome - OAB`.

        Args:
            html: Conteúdo HTML da página do processo em str.

        Returns:
            Lista de objetos `Advogado` com nome e OAB.

        Raises:
            ValueError: Se o texto do advogado não seguir o padrão `Nome - OAB`.
        """
        advogados: list[Advogado] = []
        re_nome_oab = re.compile(r'(.+?) +- +(.+)')
        for designacao, nome in self._extrair_partes(html):
            if not designacao.startswith('Advogado'):
                continue
            match = re_nome_oab.search(nome)
            if not match:
                raise ValueError('Não foi possível separar os dados do nome do advogado e OAB!')
            nome_dvogado, oab = match.groups()
            advogados.append(Advogado(nome=nome_dvogado, oab=oab))
        return advogados

    def extrair_peticoes(self, html: str) -> list[Peticao]:
        """Extrai as petições protocoladas no processo.

        Seleciona as linhas de petições do HTML e extrai número de protocolo,
        datas, tipo e peticionário de cada entrada.

        Args:
            html: Conteúdo HTML da página do processo em str.

        Returns:
            Lista de objetos `Peticao`. Retorna lista vazia se não houver petições.
        """
        soup = self._obter_soup(html)
        path_selector = 'div#idDivPeticoes > div.classDivConteudoPesquisaProcessual > div.classDivLinhaPeticoes'
        peticoes: list[Peticao] = []
        if not (linhas_peticoes := soup.select(path_selector)):
            return peticoes
        for linha in linhas_peticoes:
            tag_dados_peticao = linha.select_one('span.clsBlocoPeticaoNumTipoProtProc')
            numero_protocolo = self._extrair_texto_tag(tag_dados_peticao, 'span.classSpanLinhaPeticoesNum')
            data_protocolo = self._extrair_date_tag(tag_dados_peticao, 'span.classSpanLinhaPeticoesProtocolo')
            tipo = self._extrair_texto_tag(tag_dados_peticao, 'span.classSpanLinhaPeticoesTipo')
            data_processamento = self._extrair_date_tag(tag_dados_peticao, 'span.classSpanLinhaPeticoesProcessamento')
            peticionario = self._extrair_texto_tag(linha, 'span.classSpanLinhaPeticoesQuem')
            peticoes.append(Peticao(
                numero_protocolo=numero_protocolo, data_protocolo=data_protocolo, tipo=tipo,
                data_processamento=data_processamento, peticionario=peticionario
            ))
        return peticoes

    def extrair_pautas(self, html: str) -> list[Pauta]:
        """Extrai as pautas de julgamento associadas ao processo.

        Seleciona as linhas de pauta e extrai data/hora da sessão, órgão julgador
        e o código do documento de pauta a partir do atributo `onclick` da âncora.

        Args:
            html: Conteúdo HTML da página do processo em str.

        Returns:
            Lista de objetos `Pauta`. Retorna lista vazia se não houver pautas.

        Raises:
            ValueError: Se algum campo obrigatório da pauta não puder ser extraído.
        """
        soup = self._obter_soup(html)
        path_selector = (
            'div#idDivPautas > div.classDivConteudoPesquisaProcessual > div#idCorpoCabecalhoPautas '
            '> div#idCorpoPautas > div.clsDivLinhaPautas > span.clsBlocoPautaLinha'
        )
        pautas: list[Pauta] = []
        if not (linhas_pautas := soup.select(path_selector)):
            return pautas
        for linha in linhas_pautas:
            data_sessao = self._extrair_texto_tag(linha, 'span.clsLinhaPautasDataJulgamento')
            hora_sessao = self._extrair_texto_tag(linha, 'span.clsLinhaPautasHoraJulgamento')
            orgao_julgador = self._extrair_texto_tag(linha, 'span.clsLinhaPautasOrgaoJulgamento')
            tag_documento = linha.select_one('a[onclick^="quandoClicaDocumentoDePautaWeb"]')

            cod_documento = ''
            if tag_documento:
                re_cod_documento = r'quandoClicaDocumentoDePautaWeb\(\'([\d+]+)\'\)'
                if (match := re.search(re_cod_documento, str(tag_documento['onclick']))):
                    cod_documento = match.group(1)

            if not (data_sessao and hora_sessao and orgao_julgador and tag_documento and cod_documento):
                raise ValueError('Não foi possivel obter dados da pauta!')

            pautas.append(Pauta(
                data_sessao=self._parse_date(data_sessao + ' ' + hora_sessao),
                orgao_julgador=orgao_julgador,
                documento=Documento(
                    identificador_unico=cod_documento,
                    descricao=None,
                    link=f'/processo/pauta/buscar/?seq_documento={cod_documento}',
                    path_arquivo=''
                ),
            ))
        return pautas

    def extrair_movimentos(self, html: str) -> list[Movimento]:
        """Extrai os movimentos (andamentos) registrados no processo.

        Seleciona as linhas de movimentos do HTML e extrai data, descrição
        e documentos anexos de cada entrada.

        Args:
            html: Conteúdo HTML da página do processo em str.

        Returns:
            Lista de objetos `Movimento`. Retorna lista vazia se não houver movimentos.

        Raises:
            ValueError: Se data ou descrição de um movimento não puderem ser extraídos.
        """
        soup = self._obter_soup(html)
        path_selector = 'div#idDivFases > div.classDivConteudoPesquisaProcessual > div.classDivFaseLinha'
        movimentos: list[Movimento] = []
        if not (linhas_movimentos := soup.select(path_selector)):
            return movimentos
        for linha in linhas_movimentos:
            data = self._extrair_texto_tag(linha, 'span.clsFaseDataHora')
            texto = self._extrair_texto_tag(linha, 'span.classSpanFaseTexto')

            if not (data and texto):
                raise ValueError('Não foi possível extrair dados do movimento!')

            movimentos.append(Movimento(
                data=self._parse_date(data),
                descricao=texto,
                documentos=self._extrair_documentos_movimento(linha)
            ))
        return sorted(movimentos, reverse=True)

    def extrair_quantidade_total_movimentos(self, html: str) -> int | None:
        """Extrai o total de movimentos registrados no processo.

        Lê o campo hidden `idHddPaginacaofasesNumTotalRegistros` do formulário
        de paginação, que armazena o contador total de movimentos independente
        da página atual.

        Args:
            html: Conteúdo HTML da página do processo em str.

        Returns:
            Total de movimentos do processo. Retorna `1` se o campo hidden
            não for encontrado.

        Raises:
            ValueError: Se o bloco do formulário de paginação não for encontrado.
        """
        soup = self._obter_soup(html)
        path_selector = 'div#idDivFormularioCamposBloco'
        if not (tag_formulario := soup.select_one(path_selector)):
            raise ValueError('Não foi possivel extrair a quantidade total de movimentos!')
        input_total_movimentos = tag_formulario.select_one('input#idHddPaginacaofasesNumTotalRegistros')
        if not input_total_movimentos:
            return None
        quantidade_total_movimentos = int(str(input_total_movimentos['value']).strip())
        return quantidade_total_movimentos

    def extrair_quantidade_paginas(self, html: str) -> int:
        """Calcula o número total de páginas de movimentos do processo.

        Divide o total de movimentos pela quantidade de movimentos exibidos
        na página atual, arredondando para cima quando há resto.

        Args:
            html: Conteúdo HTML da página do processo em str.

        Returns:
            Número total de páginas. Retorna `1` se não houver movimentos
            na página atual ou se o total de movimentos não puder ser obtido.
        """
        soup = self._obter_soup(html)
        path_selector = (
            'div#idDivFases > div.classDivConteudoPesquisaProcessual > div.classDivFaseLinha'
        )
        linhas_movimentos = soup.select(path_selector)
        quantidade_movimentos_pagina = len(linhas_movimentos) if linhas_movimentos else 0
        if quantidade_movimentos_pagina == 0:
            return 1
        quantidade_total_movimentos = self.extrair_quantidade_total_movimentos(html)
        if not quantidade_total_movimentos:
            return 1
        quantidade_paginas = quantidade_total_movimentos // quantidade_movimentos_pagina
        if (quantidade_total_movimentos % quantidade_movimentos_pagina) > 0:
            quantidade_paginas += 1
        return quantidade_paginas

    def _extrair_documentos_movimento(self, linha_movimento: Tag) -> list[Documento]:
        """Extrai os documentos anexados a uma linha de movimento.

        Localiza o bloco de documentos dentro da linha e extrai descrição,
        link e identificador único de cada documento via regex no `onclick`.

        Args:
            linha_movimento: Tag HTML correspondente à linha do movimento.

        Returns:
            Lista de objetos `Documento`. Retorna lista vazia se não houver documentos.

        Raises:
            ValueError: Se o bloco de documentos existir mas não contiver linhas,
                ou se descrição ou link de algum documento não puderem ser extraídos.
        """
        path_selector = 'div.classDivLinhaFaseDocumentos'
        documentos: list[Documento] = []
        if not (tag_documentos := linha_movimento.select_one(path_selector)):
            return documentos

        path_selector_documentos = 'div.clsFaseMonocraticasLinha, div.clsFaseIntTeorRevistaLinha'
        if not (linhas_documentos := tag_documentos.select(path_selector_documentos)):
            raise ValueError('Não foi possível obter os documentos do movimento!')

        regex_link = r'abrirDocumento\(\'([^\']+)'
        for linha in linhas_documentos:
            descricao = self._extrair_texto_tag(linha)
            tag_anchor = linha.select_one('a')
            link = ''
            if tag_anchor and (match_link := re.search(regex_link, str(tag_anchor.get('onclick', '')))):
                link = match_link.group(1)
                id_doc = re.sub(r'\D', '', link)
            if not (descricao and link):
                raise ValueError('Não foi possível obter os dados do documento do movimento!')
            documentos.append(Documento(
                identificador_unico=id_doc,
                descricao=descricao,
                link=link
            ))
        return documentos

    def _extrair_partes(self, html: str) -> Generator[tuple[str, str], None, None]:
        """Gera pares (designação, nome) para cada parte ou advogado listado no processo.

        Itera sobre as linhas de partes/advogados/procuradores do HTML e
        normaliza a designação para title case sem pontuação final.

        Args:
            html: Conteúdo HTML da página do processo em str.

        Yields:
            Tupla (designacao, nome) para cada entrada encontrada.

        Raises:
            ValueError: Se designação ou nome de alguma linha não puderem ser extraídos.
        """
        soup = self._obter_soup(html)
        path_selector = (
            'div.classDivConteudoPesquisaProcessual > span#idProcessoDetalhesBloco1 '
            '> div#idDetalhesPartesAdvogadosProcuradores > div.classDivLinhaDetalhes'
        )
        if not (linhas_partes := soup.select(path_selector)):
            return
        for linha in linhas_partes:
            designacao = self._extrair_texto_tag(linha, 'span.classSpanDetalhesLabel')
            if not designacao:
                raise ValueError('Designaçao da parte não encontrada!')
            designacao = self._remover_pontuacao(designacao.title())
            nome = self._extrair_texto_tag(linha, 'span.classSpanDetalhesTexto')
            if not nome:
                raise ValueError('Nome da parte não encontrada!')
            yield (designacao, nome)
        return

    def _verificar_existencia(self, soup: BeautifulSoup) -> None:
        """Verifica se o HTML indica que nenhum registro foi encontrado.

        Args:
            soup: Objeto BeautifulSoup já parseado da página.

        Raises:
            NenhumRegistroEncontradoException: Se a mensagem de "nenhum registro
                encontrado" for detectada no HTML.
        """
        path_selector = 'div#idDivBlocoMensagem > div.clsMensagemLinha'
        if (msg := self._extrair_texto_tag(soup, path_selector)) and msg.lower() == 'nenhum registro encontrado!':
            raise NenhumRegistroEncontradoException()

    def _extrair_numero_stj(self, soup: BeautifulSoup) -> str | None:
        """Extrai o número do processo no STJ (ex: 'REsp 1234567').

        Aplica regex no texto do elemento de descrição do processo para
        localizar o padrão `Classe nº Número`.

        Args:
            soup: Objeto BeautifulSoup já parseado da página.

        Returns:
            String no formato `'Classe Número'`, ou `None` se não encontrado.
        """
        path_selector_tag = (
            'div#idDescricaoProcesso > span#idSpanClasseDescricaoNumeroRegistro > span#idSpanClasseDescricao'
        )
        if not (texto_com_numero_stj := self._extrair_texto_tag(soup, path_selector_tag)):
            return None
        regex_numero_stj = r'([A-z]+) +nº +(\d+)'
        match = re.search(regex_numero_stj, texto_com_numero_stj)
        if match:
            return ' '.join(match.groups())
        return None

    def _extrair_registro_stj(self, soup: BeautifulSoup) -> str | None:
        """Extrai o número de registro interno do processo no STJ.

        Localiza a tag de registro via seletor CSS e aplica regex para isolar
        o número no formato `AAAA/NNNNNNN-D` (ex: `2023/0123456-7`).

        Args:
            soup: Objeto BeautifulSoup já parseado da página.

        Returns:
            String com o número de registro no formato `AAAA/NNNNNNN-D`.

        Raises:
            ValueError: Se a tag de registro não for encontrada ou o texto
                não corresponder ao padrão esperado.
        """
        path_selector_tag = (
            'div#idDescricaoProcesso > span#idSpanClasseDescricaoNumeroRegistro > span#idSpanNumeroRegistro'
        )
        tag_com_registro_stj = soup.select_one(path_selector_tag)
        texto_com_registro_stj = self._extrair_texto_tag(tag_com_registro_stj)
        regex_num_registro_stj = r'(\d{4}/\d+-\d+)'
        match = re.search(regex_num_registro_stj, texto_com_registro_stj or '')
        if not (tag_com_registro_stj and match):
            raise ValueError('Não foi possível extrair o Número de Registro STJ do processo!')
        return match.group(1)

    def _obter_detalhes(self, soup: BeautifulSoup, bloco: int) -> dict[str, Tag]:
        """Extrai as linhas de um bloco de detalhes e retorna um dicionário label → Tag.

        Os labels são normalizados para caixa alta para reduzir sensibilidade
        a variações de capitalização no HTML.

        Args:
            soup: Objeto BeautifulSoup já parseado da página.
            bloco: Número do bloco de detalhes a extrair (1, 2 ou 3).

        Returns:
            Dicionário mapeando o texto do label (em caixa alta) para a
            Tag HTML com o valor correspondente.

        Raises:
            ValueError: Se o label ou a tag de valor de alguma linha não forem encontrados.
        """
        path_selector = (
            f'div.classDivConteudoPesquisaProcessual > span#idProcessoDetalhesBloco{bloco} > div.classDivLinhaDetalhes'
        )
        linhas_detalhes = soup.select(path_selector)
        detalhes_bloco: dict[str, Tag] = {}
        for linha in linhas_detalhes:
            label = self._extrair_texto_tag(linha, 'span.classSpanDetalhesLabel')
            if label is None:
                raise ValueError('Label detalhe não encontrada!')
            label = label.upper()
            tag_detalhe = linha.select_one('span.classSpanDetalhesTexto')
            if not tag_detalhe:
                raise ValueError('Tag com valor do detalhe não encontrada!')
            detalhes_bloco[label] = tag_detalhe
        return detalhes_bloco

    def _extrair_assuntos(self, tag: Tag | None) -> list[str]:
        """Extrai a lista de assuntos classificados no processo.

        Args:
            tag: Tag HTML contendo os spans de assuntos, ou `None`.

        Returns:
            Lista de strings com os assuntos sem pontuação final.
            Retorna lista vazia se `tag` for `None`.

        Raises:
            ValueError: Se um span de assunto existir mas estiver vazio.
        """
        assuntos: list[str] = []
        if not tag:
            return assuntos
        tags_assuntos = tag.select('span#idProcessoDetalheAssuntos > span')
        for tag in tags_assuntos:
            assunto = self._extrair_texto_tag(tag)
            if not assunto:
                raise ValueError('Assunto inesperado!')
            assuntos.append(self._remover_pontuacao(assunto))
        return assuntos

    def _extrair_numeros_origem(self, tag: Tag | None) -> list[str]:
        """Extrai os números de origem do processo nos tribunais inferiores.

        Args:
            tag: Tag HTML contendo as âncoras com os números de origem, ou `None`.

        Returns:
            Lista de strings com os números de origem.
            Retorna lista vazia se `tag` for `None`.

        Raises:
            ValueError: Se uma âncora de número de origem existir mas estiver vazia.
        """
        numeros: list[str] = []
        if not tag:
            return numeros
        tags_numeros = tag.select('a')
        for tag in tags_numeros:
            numero = self._extrair_texto_tag(tag)
            if not numero:
                raise ValueError('Número de origem não encontrado!')
            numeros.append(numero)
        return numeros

    def _extrair_date_tag(self, tag: Tag | BeautifulSoup | None, selector: str = '') -> datetime | None:
        """Extrai e converte o texto de uma tag para `datetime`.

        Combina `_extrair_texto_tag` e `_parse_date`. Retorna `None` se
        o texto não puder ser extraído.

        Args:
            tag: Tag HTML ou objeto BeautifulSoup de onde extrair o texto.
            selector: Seletor CSS opcional para localizar uma subtag.

        Returns:
            Objeto `datetime` convertido, ou `None` se o texto estiver ausente.
        """
        texto_tag = self._extrair_texto_tag(tag, selector)
        return self._parse_date(texto_tag) if texto_tag else None

    def _extrair_texto_tag(self, tag: Tag | BeautifulSoup | None, selector: str = '') -> str | None:
        """Extrai e normaliza o texto de uma tag HTML.

        Se um seletor for fornecido, localiza a subtag antes de extrair.
        Espaços múltiplos e quebras de linha são normalizados para um único espaço.

        Args:
            tag: Tag HTML ou objeto BeautifulSoup de onde extrair o texto.
            selector: Seletor CSS opcional para localizar uma subtag.

        Returns:
            Texto normalizado da tag, ou `None` se a tag for `None` ou
            a subtag não for encontrada pelo seletor.
        """
        if tag:
            if selector and (sub_tag := tag.select_one(selector)):
                texto = sub_tag.get_text(separator=' ', strip=True)
            else:
                texto = tag.get_text(separator=' ', strip=True)
            return self._normalizar_texto(texto)
        return None

    def _normalizar_texto(self, texto: str) -> str:
        """Normaliza espaços em branco consecutivos para um único espaço.

        Args:
            texto: String a ser normalizada.

        Returns:
            String com espaços múltiplos colapsados e sem espaços nas extremidades.
        """
        return re.sub(r'\s+', ' ', texto.strip())

    def _remover_pontuacao(self, texto: str) -> str:
        """Remove pontuação final (`.`, `,`, `:`) do texto.

        Args:
            texto: String a ser processada.

        Returns:
            String sem pontuação no final.
        """
        return re.sub(r'[.,:]\Z', '', texto.strip())

    def _obter_soup(self, html: str) -> BeautifulSoup:
        """Cria um objeto BeautifulSoup a partir do HTML em str.

        Utiliza o parser `lxml` para melhor desempenho. Este método é
        automaticamente memorizado com `lru_cache` na instância (ver `__init__`).

        Args:
            html: Conteúdo HTML em str.

        Returns:
            Objeto `BeautifulSoup` pronto para consulta.
        """
        return BeautifulSoup(html, 'lxml')

    def _parse_date(self, date: str) -> datetime:
        """Converte uma string de data para `datetime` com fuso horário.

        Tenta os formatos `%d/%m/%Y`, `%d/%m/%Y %H:%M` e `%d/%m/%Y %H:%M:%S`
        em ordem. O resultado é convertido para o fuso horário configurado em
        `TIME_ZONE`.

        Args:
            date: String com a data a ser convertida.

        Returns:
            Objeto `datetime` com fuso horário aplicado.

        Raises:
            ValueError: Se a string não corresponder a nenhum dos formatos
                suportados ou for vazia/nula.
        """
        formats = ('%d/%m/%Y', '%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S')
        if date is None or date.strip() == '':
            raise ValueError('Formato de data inesperado inválida!')
        for f in formats:
            try:
                return datetime.strptime(date.strip(), f).astimezone(TIME_ZONE)
            except ValueError as e:
                excecao = e
        raise excecao
