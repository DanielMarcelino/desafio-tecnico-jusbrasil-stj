import json

from unittest import TestCase, mock
from time import time
from typing import ClassVar

from models import BaseModelPersistente, SolucaoAntigate
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
