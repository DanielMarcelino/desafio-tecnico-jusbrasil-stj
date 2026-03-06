from pathlib import Path

from configuracoes import LOCAL_STORAGE_ROOT_PATH


class Storage:
    """Abstração para persistência de arquivos no sistema de arquivos local.

    Todos os caminhos são relativos à raiz configurada em
    `LOCAL_STORAGE_ROOT_PATH`. Diretórios intermediários são criados
    automaticamente quando necessário ao salvar um arquivo.

    Example:
        storage = Storage()
        storage.salvar_arquivo('0123456/acordao/doc.pdf', conteudo)
        conteudo = storage.obter_arquivo('0123456/acordao/doc.pdf')
        existe = storage.existe('0123456/acordao/doc.*', wildcard=True)
    """
    def salvar_arquivo(self, path_arquivo: str, content: bytes) -> None:
        """Persiste o conteúdo binário no caminho especificado.

        Se o diretório de destino não existir, ele é criado automaticamente
        antes de tentar salvar novamente.

        Args:
            path_arquivo: Caminho relativo do arquivo dentro do storage
                (ex: `'0123456/acordao/doc.pdf'`).
            content: Conteúdo binário a ser gravado no arquivo.
        """
        try:
            self._salvar_arquivo(path_arquivo, content)
        except FileNotFoundError:
            self._criar_diretorio(path_arquivo)
            self._salvar_arquivo(path_arquivo, content)

    def obter_arquivo(self, path_arquivo: str) -> bytes | None:
        """Lê e retorna o conteúdo binário do arquivo especificado.

        Args:
            path_arquivo: Caminho relativo do arquivo dentro do storage.

        Returns:
            Conteúdo binário do arquivo, ou `None` se o arquivo não existir.
        """
        path_completo = self._obter_path_completo(path_arquivo)
        p = Path(path_completo)
        try:
            with p.open('rb') as f:
                return f.read()
        except FileNotFoundError:
            return None

    def existe(self, path_arquivo: str, wildcard=False) -> bool:
        """Verifica se um arquivo existe no storage.

        Com `wildcard=True`, usa `Path.glob` para verificar a existência de
        arquivos que correspondam ao padrão - útil quando a extensão do arquivo
        não é conhecida previamente (ex: `'0123456.*'`).

        Args:
            path_arquivo: Caminho relativo do arquivo ou padrão glob
                (ex: `'0123456/doc.pdf'` ou `'0123456/doc.*'`).
            wildcard: Se `True`, interpreta `path_arquivo` como padrão glob.
                Se `False`, verifica a existência exata do caminho.

        Returns:
            `True` se o arquivo existir, `False` caso contrário.
        """
        if wildcard:
            path_completo = self._obter_path_completo('')
            return any(Path(path_completo).glob(path_arquivo))
        else:
            path_completo = self._obter_path_completo(path_arquivo)
            return Path(path_completo).exists()

    def _salvar_arquivo(self, path_arquivo: str, content: bytes) -> bool:
        """Grava o conteúdo binário no caminho completo do arquivo.

        Args:
            path_arquivo: Caminho relativo do arquivo dentro do storage.
            content: Conteúdo binário a ser gravado.

        Returns:
            `True` após gravação bem-sucedida.

        Raises:
            FileNotFoundError: Se o diretório de destino não existir.
        """
        path_completo = self._obter_path_completo(path_arquivo)
        p = Path(path_completo)
        with p.open('wb') as f:
            f.write(content)
        return True

    def _criar_diretorio(self, path_arquivo: str) -> bool:
        """Cria o diretório pai do arquivo, incluindo diretórios intermediários.

        Args:
            path_arquivo: Caminho relativo do arquivo cujo diretório pai
                deve ser criado.

        Returns:
            `True` após criação bem-sucedida.
        """
        path_completo = self._obter_path_completo(path_arquivo)
        p = Path(path_completo)
        p.parent.mkdir(parents=True, exist_ok=True)
        return True

    def _obter_path_completo(self, path_arquivo: str) -> str:
        """Compõe o caminho absoluto do arquivo a partir da raiz do storage.

        Args:
            path_arquivo: Caminho relativo do arquivo dentro do storage.

        Returns:
            Caminho absoluto no formato `LOCAL_STORAGE_ROOT_PATH/path_arquivo`.
        """
        return f'{LOCAL_STORAGE_ROOT_PATH}/{path_arquivo}'
