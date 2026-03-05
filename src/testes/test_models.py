import json

from datetime import datetime
from unittest import TestCase, mock
from time import time
from typing import ClassVar

from models import (
    BaseModelPersistente,
    SolucaoAntigate,
    Processo,
    DetalhesProcesso,
    DadosProcesso,
    Movimento
)
from storage import Storage


class TestBaseModelPersistente(TestCase):
    class ModelConcretoStub(BaseModelPersistente):
        PATH_ARQUIVO: ClassVar[str] = "modelo_teste.json"
        nome: str
        valor: int

    def setUp(self):
        self.storage_mock = mock.create_autospec(spec=Storage, instance=True)
        self.model = self.ModelConcretoStub(nome="teste", valor=42)

    def test_persistir_no_storage__chama_salvar_arquivo(self):
        """Deve chamar salvar_arquivo com o path e conteúdo corretos."""
        self.model.persistir_no_storage(self.storage_mock)

        self.storage_mock.salvar_arquivo.assert_called_once_with(
            path_arquivo="modelo_teste.json",
            content=self.model.model_dump_json().encode(),
        )

    def test_obter_do_storage___retorna_model(self):
        """Deve retornar instância do model quando arquivo existe."""
        dados = json.dumps({"nome": "teste", "valor": 42}).encode()
        self.storage_mock.obter_arquivo.return_value = dados

        resultado = self.ModelConcretoStub.obter_do_storage(self.storage_mock)

        self.assertIsInstance(resultado, self.ModelConcretoStub)
        self.assertEqual(resultado.nome, "teste")
        self.assertEqual(resultado.valor, 42)

    def test_obter_do_storage_retorna_none_quando_arquivo_nao_existe(self):
        """Deve retornar None quando o arquivo não existe no storage."""
        self.storage_mock.obter_arquivo.return_value = None

        resultado = self.ModelConcretoStub.obter_do_storage(self.storage_mock)

        self.assertIsNone(resultado)

    def test_obter_do_storage_chama_obter_arquivo_com_path_correto(self):
        """Deve chamar obter_arquivo com o PATH_ARQUIVO correto."""
        self.storage_mock.obter_arquivo.return_value = None

        self.ModelConcretoStub.obter_do_storage(self.storage_mock)

        self.storage_mock.obter_arquivo.assert_called_once_with(
            path_arquivo="modelo_teste.json"
        )

    def test_persistir_e_obter_roundtrip(self):
        """Deve persistir e recuperar o model com os mesmos dados."""
        conteudo_salvo = None

        def salvar_arquivo(path_arquivo, content):
            nonlocal conteudo_salvo
            conteudo_salvo = content

        def obter_arquivo(path_arquivo):
            return conteudo_salvo

        self.storage_mock.salvar_arquivo.side_effect = salvar_arquivo
        self.storage_mock.obter_arquivo.side_effect = obter_arquivo

        self.model.persistir_no_storage(self.storage_mock)
        recuperado = self.ModelConcretoStub.obter_do_storage(self.storage_mock)

        self.assertEqual(recuperado.nome, self.model.nome)
        self.assertEqual(recuperado.valor, self.model.valor)


class TestSolucaoAntigate(TestCase):

    def _criar_solucao(self, tempo_de_vida: int) -> SolucaoAntigate:
        return SolucaoAntigate(
            user_agent="Mozilla/5.0",
            cookies="session=abc123",
            tempo_de_vida=tempo_de_vida,
        )

    def test_path_arquivo(self):
        """PATH_ARQUIVO deve ser dados_solucao.json."""
        self.assertEqual(SolucaoAntigate.PATH_ARQUIVO, "dados_solucao_turnstile.json")

    def test_expirou__retorna_false_quando_solucao_valida(self):
        """Deve retornar False quando a solução ainda não expirou."""
        tempo_futuro = int(time()) + 3600  # 1 hora no futuro
        solucao = self._criar_solucao(tempo_futuro)

        self.assertFalse(solucao.expirou)

    def test_expirou__retorna_true_quando_solucao_expirada(self):
        """Deve retornar True quando a solucao já expirou."""
        tempo_passado = int(time()) - 3600  # 1 hora no passado
        solucao = self._criar_solucao(tempo_passado)

        self.assertTrue(solucao.expirou)

    def test_expirou__retorna_true_quando_tempo_igual_ao_atual(self):
        """Deve retornar True quando tempo_de_vida é igual ao timestamp atual."""
        timestamp_fixo = 1000000

        with mock.patch("models.time") as mock_time:
            mock_time.return_value = timestamp_fixo
            solucao = self._criar_solucao(timestamp_fixo)

            self.assertTrue(solucao.expirou)

    def test_expirou__usa_timestamp_atual(self):
        """Deve comparar com o timestamp no momento da chamada."""
        timestamp_fixo = 1000000

        with mock.patch("models.time") as mock_time:
            mock_time.return_value = timestamp_fixo
            solucao = self._criar_solucao(timestamp_fixo + 1)

            self.assertFalse(solucao.expirou)

            mock_time.return_value = timestamp_fixo + 2
            self.assertTrue(solucao.expirou)

    def test_instancia_com_atributos_corretos(self):
        """Deve criar a instância com os atributos fornecidos."""
        solucao = self._criar_solucao(9999999999)

        self.assertEqual(solucao.user_agent, "Mozilla/5.0")
        self.assertEqual(solucao.cookies, "session=abc123")
        self.assertEqual(solucao.tempo_de_vida, 9999999999)


class TestProcesso(TestCase):
    def _criar_detalhes(self) -> DetalhesProcesso:
        return DetalhesProcesso(
            numero_stj='Ag 1280821',
            registro_stj='2010/0034356-3',
            numero_cnj='0049393-26.2026.3.00.0000',
            classe='AGRAVO DE INSTRUMENTO',
            localizacao='Saída para PROCESSO ELETRÔNICO BAIXADO em 20/04/2010',
            tipo='Processo eletrônico',
            autuacao=datetime(2026, 1, 1),
            relator='Min. MASSAMI UYEDA - TERCEIRA TURMA',
            ramo_do_direito='DIREITO CIVIL',
            assuntos=['DIREITO CIVIL', 'Obrigações', 'Espécies de Contratos', 'Contratos Bancários'],
            tribunal_origem='TRIBUNAL DE JUSTIÇA DO ESTADO DE MINAS GERAIS',
            volume_apenso='1 volume, nenhum apenso',
            numeros_de_origem=['10024094862315', '10024094862315003', '10024094862315004']
        )

    def _criar_movimento(self, data: str, descricao: str) -> Movimento:
        return Movimento(data=datetime.strptime(data, '%Y-%m-%d'), descricao=descricao, documentos=[])

    def _criar_dados(self) -> DadosProcesso:
        return DadosProcesso(
            detalhes=self._criar_detalhes(), partes=[], advogados=[], peticoes=[], pautas=[], movimentos=[],
            ultima_atualizacao=datetime(2026, 1, 1)
        )

    def setUp(self):
        self.mock_storage = mock.create_autospec(spec=Storage, instance=True)
        return super().setUp()

    # Testes criar
    def test_criar__quando_dados_sao_validos__cria_instancia_processo_com_dados(self):
        dados = self._criar_dados()
        processo_criado = Processo.criar(dados=dados)

        self.assertIsInstance(processo_criado, Processo)
        self.assertDictEqual(dados.model_dump(), processo_criado.dados.model_dump())

    def test_criar__ao_criar_processo__ordena_movimentos_em_ordem_decrescente_(self):
        movimento_dia_1 = self._criar_movimento('2026-01-01', 'Texto movimento dia 1')
        movimento_dia_2 = self._criar_movimento('2026-01-02', 'Texto movimento dia 2')
        movimento_dia_3 = self._criar_movimento('2026-01-03', 'Texto movimento dia 3')

        dados = self._criar_dados()
        dados.movimentos = [movimento_dia_1, movimento_dia_2, movimento_dia_3]
        processo_criado = Processo.criar(dados=dados)

        self.assertEqual([movimento_dia_3, movimento_dia_2, movimento_dia_1], processo_criado.dados.movimentos)

    # Testes carregar
    def test_carregar__recupera_processo_armazenado(self):
        processo_armazenado = Processo(dados=self._criar_dados())
        self.mock_storage.obter_arquivo.return_value = processo_armazenado.model_dump_json().encode()
        processo_carregado = Processo.carregar(storage=self.mock_storage, registro_stj='2010/0034356-3')

        self.mock_storage.obter_arquivo.assert_called_once_with(path_arquivo='201000343563/dados_processo.json')
        self.assertDictEqual(processo_armazenado.model_dump(), processo_carregado.model_dump())

    def test_carregar__quando_processo_nao_existe_no_armazenamento__retorna_none(self):
        self.mock_storage.obter_arquivo.return_value = None
        processo_carregado = Processo.carregar(storage=self.mock_storage, registro_stj='2010/0034356-3')

        self.mock_storage.obter_arquivo.assert_called_once_with(path_arquivo='201000343563/dados_processo.json')
        self.assertIsNone(processo_carregado)

    # Testes atualizar
    def test_atualizar__atualiza_dados(self):
        processo = Processo(dados=self._criar_dados())

        novos_dados = self._criar_dados()
        novos_dados.detalhes.localizacao = 'Nova Localizacao'
        novos_dados.detalhes.relator = 'Novo relator'

        processo.atualizar(dados=novos_dados)

        self.assertDictEqual(novos_dados.model_dump(), processo.dados.model_dump())

    def test_atualizar__mescla_movimentos(self):
        processo = Processo(dados=self._criar_dados())

        movimento_dia_2 = self._criar_movimento('2026-01-02', 'Texto movimento dia 2')
        movimento_dia_1 = self._criar_movimento('2026-01-01', 'Texto movimento dia 1')
        processo.dados.movimentos = [movimento_dia_2, movimento_dia_1]

        novos_dados = self._criar_dados()
        movimento_dia_3 = self._criar_movimento('2026-01-03', 'Texto movimento dia 3')
        novos_dados.movimentos = [movimento_dia_3, movimento_dia_2]

        processo.atualizar(dados=novos_dados)

        self.assertEqual([movimento_dia_3, movimento_dia_2, movimento_dia_1], processo.dados.movimentos)

    def test_atualizar__ao_atualizar_processo__ordena_movimentos_em_ordem_decrescente_(self):
        processo = Processo(dados=self._criar_dados())

        novo_dados = self._criar_dados()
        movimento_dia_1 = self._criar_movimento('2026-01-01', 'Texto movimento dia 1')
        movimento_dia_2 = self._criar_movimento('2026-01-02', 'Texto movimento dia 2')
        movimento_dia_3 = self._criar_movimento('2026-01-03', 'Texto movimento dia 3')
        novo_dados.movimentos = [movimento_dia_1, movimento_dia_2, movimento_dia_3]

        processo.atualizar(dados=novo_dados)

        self.assertEqual([movimento_dia_3, movimento_dia_2, movimento_dia_1], processo.dados.movimentos)

    # Testes salvar
    def test_salvar__salva_model_no_storage(self):
        processo = Processo(dados=self._criar_dados())

        processo.salvar(storage=self.mock_storage)

        self.mock_storage.salvar_arquivo.assert_called_once_with(
            path_arquivo='201000343563/dados_processo.json',
            content=processo.model_dump_json().encode()
        )

    # Testes id_processo
    def test_id_processo__gera_id_com_numero_registro_stj(self):
        processo = Processo(dados=self._criar_dados())

        self.assertEqual('201000343563', processo.id_processo)
