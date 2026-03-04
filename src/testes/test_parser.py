from datetime import datetime
from functools import lru_cache
from pathlib import Path
from unittest import TestCase, mock

from freezegun import freeze_time

from configuracoes import TIME_ZONE
from parser import Parser, NenhumRegistroEncontradoException
from models import DadosProcesso, DetalhesProcesso, Parte, Advogado, Peticao, Pauta, Movimento, Documento


@lru_cache()
def obtem_fixture(path: str) -> bytes:
    p = Path('src/testes/fixtures').joinpath(path)
    with p.open('rb') as f:
        conteudo_fixture: bytes = f.read()
    return conteudo_fixture


def obtem_datetime(ano: int, mes: int, dia: int, hora: int = 0, min: int = 0, seg: int = 0) -> datetime:
    return datetime(ano, mes, dia, hora, min, seg, tzinfo=TIME_ZONE)


def criar_detalhes() -> DadosProcesso:
    return DetalhesProcesso(
        numero_stj='fake', registro_stj='fake', numero_cnj='fake', classe='fake', localizacao='fake',
        tipo='fake', autuacao=obtem_datetime(2026, 1, 1), relator='fake', ramo_do_direito='fake',
        assuntos=[], tribunal_origem='fake', volume_apenso='fake', numeros_de_origem=[]
    )


def criar_partes() -> list[Parte]:
    return [Parte(designacao='fake', nome='fake'), Parte(designacao='fake', nome='fake')]


def criar_advogados() -> list[Advogado]:
    return [Advogado(nome='fake', oab='fake'), Advogado(nome='fake', oab='fake')]


def criar_peticoes() -> list[Peticao]:
    return [
        Peticao(
            numero_protocolo='fake', data_protocolo=obtem_datetime(2026, 1, 1), tipo='fake',
            data_processamento=obtem_datetime(2026, 1, 1), peticionario='fake'
        ),
        Peticao(
            numero_protocolo='fake', data_protocolo=obtem_datetime(2026, 1, 1), tipo='fake',
            data_processamento=obtem_datetime(2026, 1, 1), peticionario='fake'
        ),
    ]


def criar_pautas() -> list[Pauta]:
    return [
        Pauta(
            data_sessao=obtem_datetime(2026, 1, 1), orgao_julgador='fake',
            documento=Documento(identificador_unico='fake', descricao=None, link='fake', path_arquivo=None)
        ),
        Pauta(
            data_sessao=obtem_datetime(2026, 1, 1), orgao_julgador='fake',
            documento=Documento(identificador_unico='fake', descricao=None, link='fake', path_arquivo=None)
        ),
    ]


def criar_movimentos() -> list[Pauta]:
    return [
        Movimento(data=obtem_datetime(2026, 1, 1), descricao='fake', documentos=[]),
        Movimento(data=obtem_datetime(2026, 1, 1), descricao='fake', documentos=[])
    ]


class TestParser(TestCase):
    path_fixture_nenhum_registro_encontrado = 'nenhum_registro_encontrado.html'
    path_fixture_processo_1 = 'processo_1.html'
    path_fixture_processo_1_pagina_2 = 'processo_1_pagina_2.html'
    path_fixture_processo_2 = 'processo_2.html'
    path_fixture_processo_3 = 'processo_3.html'

    def setUp(self):
        self.parser = Parser()
        return super().setUp()

    def _testar_extrair_detalhes(self, path_fixture: str, detalhes_esperados: DetalhesProcesso) -> None:
        html = obtem_fixture(path_fixture)
        detalhes_obtidos: DetalhesProcesso = self.parser.extrair_detalhes(html)

        self.assertIsInstance(detalhes_obtidos, DetalhesProcesso)

        dump_detalhes_esperados = detalhes_esperados.model_dump()
        dump_detalhes_obtidos = detalhes_obtidos.model_dump()

        for detalhe in dump_detalhes_esperados:
            with self.subTest(detalhe=detalhe):
                self.assertEqual(dump_detalhes_esperados[detalhe], dump_detalhes_obtidos[detalhe])

    def _testar_extrair_partes(self, path_fixture: str, partes_esperadas: list[Parte]) -> None:
        html = obtem_fixture(path_fixture)
        partes_obtidas: list[Parte] = self.parser.extrair_partes(html)

        self.assertIsInstance(partes_obtidas, list)

        if partes_obtidas:
            self.assertIsInstance(partes_obtidas[0], Parte)

        self.assertEqual(
            list(map(lambda p: p.model_dump(), partes_esperadas)),
            list(map(lambda p: p.model_dump(), partes_obtidas)),
        )

    def _testar_extrair_advogados(self, path_fixture: str, advogados_esperados: list[Advogado]) -> None:
        html = obtem_fixture(path_fixture)
        advogados_obtidos: list[Advogado] = self.parser.extrair_advogados(html)

        self.assertIsInstance(advogados_obtidos, list)

        if advogados_obtidos:
            self.assertIsInstance(advogados_obtidos[0], Advogado)

        self.assertEqual(
            list(map(lambda p: p.model_dump(), advogados_esperados)),
            list(map(lambda p: p.model_dump(), advogados_obtidos)),
        )

    def _testar_extrair_peticoes(self, path_fixture: str, peticoes_esperadas: list[Peticao],
                                 indices: tuple, quantidade_esperada: int) -> None:
        html = obtem_fixture(path_fixture)
        peticoes_obtidas: list[Advogado] = self.parser.extrair_peticoes(html)

        self.assertIsInstance(peticoes_obtidas, list)

        if peticoes_obtidas:
            self.assertIsInstance(peticoes_obtidas[0], Peticao)

        peticoes_testar = [peticoes_obtidas[i].model_dump() for i in indices]
        self.assertEqual(
            list(map(lambda p: p.model_dump(), peticoes_esperadas)),
            peticoes_testar,
        )
        self.assertEqual(quantidade_esperada, len(peticoes_obtidas))

    def _testar_extrair_pautas(self, path_fixture: str, pautas_esperadas: list[Peticao],
                               indices: tuple, quantidade_esperada: int) -> None:
        html = obtem_fixture(path_fixture)
        pautas_obtidas: list[Advogado] = self.parser.extrair_pautas(html)

        self.assertIsInstance(pautas_obtidas, list)

        if pautas_obtidas:
            self.assertIsInstance(pautas_obtidas[0], Pauta)

        pautas_testar = [pautas_obtidas[i].model_dump() for i in indices]
        self.assertEqual(
            list(map(lambda p: p.model_dump(), pautas_esperadas)),
            pautas_testar,
        )
        self.assertEqual(quantidade_esperada, len(pautas_obtidas))

    def _testar_extrair_movimentos(self, path_fixture: str, movimentos_esperados: list[Peticao],
                                   indices: tuple, quantidade_esperada: int) -> None:
        html = obtem_fixture(path_fixture)
        movimentos_obtidos: list[Advogado] = self.parser.extrair_movimentos(html)

        self.assertIsInstance(movimentos_obtidos, list)

        if movimentos_obtidos:
            self.assertIsInstance(movimentos_obtidos[0], Movimento)

        movimentos_testar = [movimentos_obtidos[i].model_dump() for i in indices]
        self.assertEqual(
            list(map(lambda p: p.model_dump(), movimentos_esperados)),
            movimentos_testar,
        )
        self.assertEqual(quantidade_esperada, len(movimentos_obtidos))

    # Testes extrair_quantidade_paginas
    def test_extrair_quantidade_paginas__extrai_quantidade_paginas_processo_1(self):
        html = obtem_fixture(self.path_fixture_processo_1)
        self.assertEqual(2, self.parser.extrair_quantidade_paginas(html))

    def test_extrair_quantidade_paginas__extrai_quantidade_paginas_processo_2(self):
        html = obtem_fixture(self.path_fixture_processo_2)
        self.assertEqual(1, self.parser.extrair_quantidade_paginas(html))

    def test_extrair_quantidade_paginas__extrai_quantidade_paginas_processo_3(self):
        html = obtem_fixture(self.path_fixture_processo_3)
        self.assertEqual(1, self.parser.extrair_quantidade_paginas(html))

    # Testes extrair_detalhes
    def test_extrair_detalhes__quando_processo_inexistente_lanca_excecao(self):
        html = obtem_fixture(self.path_fixture_nenhum_registro_encontrado)
        with self.assertRaises(NenhumRegistroEncontradoException):
            self.parser.extrair_detalhes(html)

    def test_extrair_detalhes__extrai_detalhes_processo_1(self):
        detalhes_esperados = DetalhesProcesso(
            numero_stj='EAREsp 2814815',
            registro_stj='2024/0449175-9',
            numero_cnj='1027558-72.2017.8.26.0053',
            classe='EMBARGOS DE DIVERGÊNCIA EM AGRAVO EM RECURSO ESPECIAL',
            localizacao='Entrada em COORDENADORIA DE PROCESSAMENTO DE FEITOS DE DIREITO PÚBLICO em 08/01/2026',
            tipo='Processo eletrônico',
            autuacao=obtem_datetime(2024, 12, 13),
            relator='Min. JOÃO OTÁVIO DE NORONHA - CORTE ESPECIAL',
            ramo_do_direito='DIREITO ADMINISTRATIVO',
            assuntos=[
                'DIREITO ADMINISTRATIVO E OUTRAS MATÉRIAS DE DIREITO PÚBLICO',
                'Ordem Urbanística', 'Segurança em Edificações'
            ],
            tribunal_origem='TRIBUNAL DE JUSTIÇA DO ESTADO DE SÃO PAULO - AV. BRIGADEIRO',
            volume_apenso='1 volume, nenhum apenso',
            numeros_de_origem=['10275587220178260053']
        )
        self._testar_extrair_detalhes(self.path_fixture_processo_1, detalhes_esperados)

    def test_extrair_detalhes__extrai_detalhes_processo_2(self):
        detalhes_esperados = DetalhesProcesso(
            numero_stj=None,
            registro_stj='2026/0049393-9',
            numero_cnj='0049393-26.2026.3.00.0000',
            classe='HABEAS CORPUS',
            localizacao='Saída para PROCESSO ENCERRADO em 13/02/2026',
            tipo='Processo eletrônico',
            autuacao=None,
            relator=None,
            ramo_do_direito=None,
            assuntos=[],
            tribunal_origem='TRIBUNAL DE JUSTIÇA DO ESTADO DE MINAS GERAIS',
            volume_apenso='nenhum volume, nenhum apenso',
            numeros_de_origem=['50159028520268130024']
        )
        self._testar_extrair_detalhes(self.path_fixture_processo_2, detalhes_esperados)

    def test_extrair_detalhes__extrai_detalhes_processo_3(self):
        detalhes_esperados = DetalhesProcesso(
            numero_stj='Ag 1280821',
            registro_stj='2010/0034356-3',
            numero_cnj=None,
            classe='AGRAVO DE INSTRUMENTO',
            localizacao='Saída para PROCESSO ELETRÔNICO BAIXADO em 20/04/2010',
            tipo='Processo eletrônico',
            autuacao=obtem_datetime(2010, 3, 10),
            relator='Min. MASSAMI UYEDA - TERCEIRA TURMA',
            ramo_do_direito='DIREITO CIVIL',
            assuntos=['DIREITO CIVIL', 'Obrigações', 'Espécies de Contratos', 'Contratos Bancários'],
            tribunal_origem='TRIBUNAL DE JUSTIÇA DO ESTADO DE MINAS GERAIS',
            volume_apenso='1 volume, nenhum apenso',
            numeros_de_origem=['10024094862315', '10024094862315003', '10024094862315004']
        )
        self._testar_extrair_detalhes(self.path_fixture_processo_3, detalhes_esperados)

    # Testes extrair_partes
    def test_extrair_partes__extrai_partes_processo_1(self):
        partes_esperadas = [
            Parte(designacao='Embargante', nome='GAFISA S/A'),
            Parte(designacao='Embargado', nome='MINISTÉRIO PÚBLICO DO ESTADO DE SÃO PAULO'),
            Parte(designacao='Interes.', nome='ERBE INCORPORADORA 019 S.A.'),
            Parte(designacao='Interes.', nome='PAULA EDUARDO INCORPORADORA E CONSTRUTORA LTDA.')
        ]
        self._testar_extrair_partes(self.path_fixture_processo_1, partes_esperadas)

    def test_extrair_partes__extrai_partes_processo_2(self):
        partes_esperadas = [
            Parte(designacao='Impetrante', nome='THAYNARA VALERIA SILVA'),
            Parte(designacao='Impetrado', nome='TRIBUNAL DE JUSTIÇA DO ESTADO DE MINAS GERAIS'),
            Parte(designacao='Paciente', nome='ELIPHAS LEVI ASSUMPCAO EGG GOMES (PRESO)')
        ]
        self._testar_extrair_partes(self.path_fixture_processo_2, partes_esperadas)

    def test_extrair_partes__extrai_partes_processo_3(self):
        partes_esperadas = [
            Parte(designacao='Agravante', nome='BANCO ABN AMRO REAL S.A'),
            Parte(designacao='Agravado', nome='SANDERSON DE OLIVEIRA'),
        ]
        self._testar_extrair_partes(self.path_fixture_processo_3, partes_esperadas)

    # Testes extrair_advogados
    def test_extrair_advogados__extrai_advogados_processo_1(self):
        advogados_esperados = [
            Advogado(nome='GUSTAVO MOTA GUEDES', oab='RJ095346'),
            Advogado(nome='GUSTAVO PINHEIRO GUIMARÃES PADILHA', oab='SP178268'),
            Advogado(nome='JULIANA LEITE DE ARAÚJO', oab='RJ154042'),
            Advogado(nome='LARISSA GUIMARÃES BENCK DE JESUS', oab='RJ235071'),
            Advogado(nome='MARIA HELENA PINTO RIBEIRO', oab='RJ256541'),
            Advogado(nome='PEDRO MOURA GUTIERREZ Y SACK', oab='RJ153470'),
            Advogado(nome='ROBERTO THEDIM DUARTE CANCELLA', oab='RJ066270'),
            Advogado(nome='ALICE BRAVO BRAILE', oab='SP408897'),
            Advogado(nome='BRUNO TOSCANI', oab='SP478453'),
            Advogado(nome='MARIA LUCIA PEREIRA CETRARO', oab='SP323922'),
            Advogado(nome='RAFAEL DE CARVALHO PASSARO', oab='SP164878'),
            Advogado(nome='FLÁVIA CRISTINA ALTERIO FALAVIGNA', oab='SP242584'),
            Advogado(nome='JÚLIA ORLANDINI ALONSO', oab='SP434421'),
            Advogado(nome='PEDRO DALDA GRAZIANO GENOVESI OLIVEIRA', oab='SP491956'),
            Advogado(nome='RODRIGO FIRMO DA SILVA PONTES', oab='SP249253')
        ]
        self._testar_extrair_advogados(self.path_fixture_processo_1, advogados_esperados)

    def test_extrair_advogados__extrai_advogados_processo_2(self):
        advogados_esperados = [
            Advogado(nome='JHEAN FLEICKER EGG GOMES', oab='MG108684'),
            Advogado(nome='THAYNARA VALERIA SILVA', oab='MG189154'),
        ]
        self._testar_extrair_advogados(self.path_fixture_processo_2, advogados_esperados)

    def test_extrair_advogados__extrai_advogados_processo_3(self):
        advogados_esperados = [
            Advogado(nome='OSMAR MENDES PAIXAO CORTES', oab='DF015553'),
            Advogado(nome='WILLIAM BATISTA NESIO E OUTRO(S)', oab='MG070580'),
            Advogado(nome='JHEAN FLEICKER EGG GOMES', oab='MG108684'),
        ]
        self._testar_extrair_advogados(self.path_fixture_processo_3, advogados_esperados)

    # Testes extrair_peticoes
    def test_extrair_peticoes__extrai_peticoes_processo_1(self):
        peticoes_esperadas = [
            Peticao(
                numero_protocolo='0150551/2026',
                data_protocolo=obtem_datetime(2026, 2, 24),
                tipo='AgInt',
                data_processamento=obtem_datetime(2026, 2, 24),
                peticionario='GAFISA S/A'
            ),
            Peticao(
                numero_protocolo='0035424/2025',
                data_protocolo=obtem_datetime(2025, 1, 21),
                tipo='ParMPF',
                data_processamento=obtem_datetime(2025, 1, 21),
                peticionario='MPF'
            )
        ]
        indices = (0, -1)
        quantidade_esperada = 18
        self._testar_extrair_peticoes(
            self.path_fixture_processo_1, peticoes_esperadas, indices, quantidade_esperada
        )

    def test_extrair_peticoes__extrai_peticoes_processo_2(self):
        peticoes_esperadas: list[Peticao] = []
        indices = ()
        quantidade_esperada = 0
        self._testar_extrair_peticoes(self.path_fixture_processo_2, peticoes_esperadas, indices, quantidade_esperada)

    def test_extrair_peticoes__extrai_peticoes_processo_3(self):
        peticoes_esperadas = [
            Peticao(
                numero_protocolo='0053753/2010',
                data_protocolo=obtem_datetime(2010, 3, 10),
                tipo='PROC',
                data_processamento=obtem_datetime(2010, 3, 18),
                peticionario='P/ BANCO SANTANDER BRASIL S.A.'
            )
        ]
        indices = (0,)
        quantidade_esperada = 1
        self._testar_extrair_peticoes(self.path_fixture_processo_3, peticoes_esperadas, indices, quantidade_esperada)

    # Testes extrair_pautas
    def test_extrair_pautas__extrai_pautas_processo_1(self):
        pautas_esperadas: list[Pauta] = [
            Pauta(
                data_sessao=obtem_datetime(2025, 8, 13),
                orgao_julgador='2ª Turma',
                documento=Documento(
                    identificador_unico='320184034', descricao=None,
                    link='/processo/pauta/buscar/?seq_documento=320184034',
                    path_arquivo=''
                )
            ),
            Pauta(
                data_sessao=obtem_datetime(2025, 10, 22),
                orgao_julgador='2ª Turma',
                documento=Documento(
                    identificador_unico='337620129', descricao=None,
                    link='/processo/pauta/buscar/?seq_documento=337620129',
                    path_arquivo=''
                )
            ),
        ]
        indices = (0, -1)
        quantidade_esperada = 4
        self._testar_extrair_pautas(self.path_fixture_processo_1, pautas_esperadas, indices, quantidade_esperada)

    def test_extrair_pautas__extrai_pautas_processo_2(self):
        pautas_esperadas: list[Pauta] = []
        indices = ()
        quantidade_esperada = 0
        self._testar_extrair_pautas(
            self.path_fixture_processo_2, pautas_esperadas, indices, quantidade_esperada
        )

    def test_extrair_pautas__extrai_pautas_processo_3(self):
        pautas_esperadas: list[Pauta] = []
        indices = ()
        quantidade_esperada = 0
        self._testar_extrair_pautas(self.path_fixture_processo_3, pautas_esperadas, indices, quantidade_esperada)

    # Testes extrair_movimentos
    def test_extrair_movimentos__extrai_movimentos_processo_1(self):
        movimentos_esperados: list[Movimento] = [
            Movimento(
                data=obtem_datetime(2026, 2, 27, 4, 48),
                descricao=(
                    'Disponibilizada intimação eletrônica (Decisões e Vistas) ao(à) MINISTÉRIO PÚBLICO FEDERAL (300105)'
                ),
                documentos=[]
            ),
            Movimento(
                data=obtem_datetime(2026, 1, 12, 0, 37),
                descricao='Publicado DESPACHO / DECISÃO em 12/01/2026 (92)',
                documentos=[
                    Documento(
                        identificador_unico='352781681202404491759202601120',
                        descricao='Decisão Monocrática - Ministro JOÃO OTÁVIO DE NORONHA',
                        link=(
                            '/processo/dj/documento/mediado/?tipo_documento=documento&componente=MON'
                            '&sequencial=352781681&tipo_documento=documento&num_registro=202404491759'
                            '&data=20260112&tipo=0'
                        ),
                        path_arquivo=None
                    )
                ]
            ),
            Movimento(
                data=obtem_datetime(2025, 10, 27, 1, 6),
                descricao='Publicado EMENTA / ACORDÃO em 27/10/2025 Petição Nº 774402/2025 - EDcl no AgInt no (92)',
                documentos=[
                    Documento(
                        identificador_unico='534285347120240449175920250077440220251027',
                        descricao='EMENTA / ACORDÃO',
                        link='/processo/julgamento/eletronico/documento/mediado/?documento_tipo=5&'
                        'documento_sequencial=342853471&registro_numero=202404491759&'
                        'peticao_numero=202500774402&publicacao_data=20251027',
                        path_arquivo=None
                    ),
                    Documento(
                        identificador_unico='9133491626620240449175920250077440220251027',
                        descricao='RELATÓRIO E VOTO - Min. MARIA THEREZA DE ASSIS MOURA',
                        link='/processo/julgamento/eletronico/documento/mediado/?documento_tipo=91'
                        '&documento_sequencial=334916266&registro_numero=202404491759'
                        '&peticao_numero=202500774402&publicacao_data=20251027',
                        path_arquivo=None
                    ),
                    Documento(
                        identificador_unico='4134285346720240449175920250077440220251027',
                        descricao='CERTIDÃO DE JULGAMENTO',
                        link='/processo/julgamento/eletronico/documento/mediado/?documento_tipo=41'
                        '&documento_sequencial=342853467&registro_numero=202404491759&peticao_numero=202500774402'
                        '&publicacao_data=20251027',
                        path_arquivo=None
                    ),
                ]
            ),
            Movimento(
                data=obtem_datetime(2025, 8, 14, 18, 30),
                descricao=(
                    'Ato ordinatório praticado - Acórdão encaminhado à publicação - Petição Nº 2025/0265576 - '
                    'AgInt no AREsp 2814815 - Publicação prevista para 18/08/2025 (11383)'
                ),
                documentos=[]
            )
        ]
        indices = (0, 12, 32, -1)
        quantidade_esperada = 100
        self._testar_extrair_movimentos(
            self.path_fixture_processo_1, movimentos_esperados, indices, quantidade_esperada
        )

    def test_extrair_movimentos__extrai_movimentos_processo_1_pagina_2(self):
        movimentos_esperados: list[Movimento] = []
        indices = ()
        quantidade_esperada = 98
        self._testar_extrair_movimentos(
            self.path_fixture_processo_1_pagina_2, movimentos_esperados, indices, quantidade_esperada
        )

    def test_extrair_movimentos__extrai_movimentos_processo_2(self):
        movimentos_esperados: list[Movimento] = []
        indices = ()
        quantidade_esperada = 2
        self._testar_extrair_movimentos(
            self.path_fixture_processo_2, movimentos_esperados, indices, quantidade_esperada
        )

    def test_extrair_movimentos__extrai_movimentos_processo_3(self):
        movimentos_esperados: list[Movimento] = []
        indices = ()
        quantidade_esperada = 17
        self._testar_extrair_movimentos(
            self.path_fixture_processo_3, movimentos_esperados, indices, quantidade_esperada
        )

    # Testes extrair_dados_processo
    @freeze_time('2026-03-03')
    def test_extrair_dados_processo__extrai_dados_e_retorna_model_dados_processos(self):
        dados_esperados = DadosProcesso(
            detalhes=criar_detalhes(), partes=criar_partes(), advogados=criar_advogados(),
            peticoes=criar_peticoes(), pautas=criar_pautas(), movimentos=criar_movimentos(),
            ultima_atualizacao=datetime.now(TIME_ZONE)
        )

        with mock.patch.object(Parser, 'extrair_detalhes', return_value=criar_detalhes()), \
             mock.patch.object(Parser, 'extrair_partes', return_value=criar_partes()), \
             mock.patch.object(Parser, 'extrair_advogados', return_value=criar_advogados()), \
             mock.patch.object(Parser, 'extrair_peticoes', return_value=criar_peticoes()), \
             mock.patch.object(Parser, 'extrair_pautas', return_value=criar_pautas()), \
             mock.patch.object(Parser, 'extrair_movimentos', return_value=criar_movimentos()):
            dados_retornados = self.parser.extrair_dados_processo(b'<html>')

        self.assertIsInstance(dados_retornados, DadosProcesso)
        self.assertDictEqual(dados_esperados.model_dump(), dados_retornados.model_dump())

    @freeze_time('2026-03-03 12:30')
    def test_extrair_dados_processo__define_ultima_atualizacao_processo_com_datetime_atual(self):
        with mock.patch.object(Parser, 'extrair_detalhes', return_value=criar_detalhes()), \
             mock.patch.object(Parser, 'extrair_partes', return_value=criar_partes()), \
             mock.patch.object(Parser, 'extrair_advogados', return_value=criar_advogados()), \
             mock.patch.object(Parser, 'extrair_peticoes', return_value=criar_peticoes()), \
             mock.patch.object(Parser, 'extrair_pautas', return_value=criar_pautas()), \
             mock.patch.object(Parser, 'extrair_movimentos', return_value=criar_movimentos()):
            dados_retornados = self.parser.extrair_dados_processo(b'<html>')

        self.assertEqual(datetime.now(TIME_ZONE), dados_retornados.ultima_atualizacao)
