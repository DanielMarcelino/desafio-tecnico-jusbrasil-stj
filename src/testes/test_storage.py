from pathlib import Path
from unittest import TestCase

from storage import Storage
from configuracoes import LOCAL_STORAGE_ROOT_PATH


class TestStorage(TestCase):
    def setUp(self):
        self.storage = Storage()
        return super().setUp()

    def _criar_arquivo(self, path_arquivo: str, content: bytes) -> None:
        path_completo = f'{LOCAL_STORAGE_ROOT_PATH}/{path_arquivo}'
        p = Path(path_completo)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('wb') as f:
            f.write(content)

    def assertArquivoExiste(self, path_arquivo: str, content: bytes) -> bool:
        path_completo = f'{LOCAL_STORAGE_ROOT_PATH}/{path_arquivo}'
        try:
            with Path(path_completo).open('rb') as f:
                content_arquivo_salvo = f.read()
            if content == content_arquivo_salvo:
                return True
            else:
                self.fail(f'O arquivo {path_completo} não contém o conteúdo esperado!')
        except FileNotFoundError:
            self.fail(f'O arquivo {path_completo} não foi encontrado!')

    def test_salvar_arquivo__quando_nao_existe__cria_novo(self):
        path = f'{self._testMethodName}/arquivo_novo.txt'
        content = b'conteudo'

        self.storage.salvar_arquivo(path, content)

        self.assertArquivoExiste(path, content)

    def test_salvar_arquivo__quando_ja_existe__sobrescreve(self):
        path = f'{self._testMethodName}/arquivo.txt'
        self._criar_arquivo(path, b'conteudo')

        self.storage.salvar_arquivo(path, b'conteudo novo')

        self.assertArquivoExiste(path, b'conteudo novo')

    def test_obter_arquivo__quando_existe__retorna_o_conteudo(self):
        path = f'{self._testMethodName}/arquivo.txt'
        content = b'conteudo'
        self._criar_arquivo(path, content)

        content_obtido = self.storage.obter_arquivo(path)

        self.assertEqual(content, content_obtido)

    def test_obter_arquivo__quando_nao_existe__retorna_none(self):
        path = f'{self._testMethodName}/arquivo.txt'
        self.assertIsNone(self.storage.obter_arquivo(path))

    def test_existe__quando_existe__retorna_true(self):
        path_sem_wildcard = f'{self._testMethodName}/arquivo.txt'
        path_com_wildcard = f'{self._testMethodName}/arquivo.*'
        self._criar_arquivo(path_sem_wildcard, b'conteudo')

        kwargs_list = (
            {'path_arquivo': path_sem_wildcard},
            {'path_arquivo': path_com_wildcard, 'wildcard': True}
        )
        for kwargs in kwargs_list:
            with self.subTest(**kwargs):
                self.assertTrue(self.storage.existe(**kwargs))

    def test_existe__quando_nao_existe__retorna_false(self):
        path_sem_wildcard = f'{self._testMethodName}/arquivo.txt'
        path_com_wildcard = f'{self._testMethodName}/arquivo.*'

        kwargs_list = (
            {'path_arquivo': path_sem_wildcard},
            {'path_arquivo': path_com_wildcard, 'wildcard': True}
        )
        for kwargs in kwargs_list:
            with self.subTest(**kwargs):
                self.assertFalse(self.storage.existe(**kwargs))
