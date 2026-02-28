from pathlib import Path

from configuracoes import LOCAL_STORAGE_ROOT_PATH


class Storage:
    def salvar_arquivo(self, path_arquivo: str, content: bytes) -> None:
        try:
            self._salvar_arquivo(path_arquivo, content)
        except FileNotFoundError:
            self._criar_diretorio(path_arquivo)
            self._salvar_arquivo(path_arquivo, content)

    def obter_arquivo(self, path_arquivo: str) -> bytes | None:
        path_completo = self._obter_path_completo(path_arquivo)
        p = Path(path_completo)
        try:
            with p.open('rb') as f:
                return f.read()
        except FileNotFoundError:
            return None

    def existe(self, path_arquivo: str, wildcard=False) -> bool:
        if wildcard:
            path_completo = self._obter_path_completo('')
            return any(Path(path_completo).glob(path_arquivo))
        else:
            path_completo = self._obter_path_completo(path_arquivo)
            return Path(path_completo).exists()

    def _salvar_arquivo(self, path_arquivo: str, content: bytes) -> bool:
        path_completo = self._obter_path_completo(path_arquivo)
        p = Path(path_completo)
        with p.open('wb') as f:
            f.write(content)
        return True

    def _criar_diretorio(self, path_arquivo: str) -> bool:
        path_completo = self._obter_path_completo(path_arquivo)
        p = Path(path_completo)
        p.parent.mkdir(parents=True, exist_ok=True)
        return True

    def _obter_path_completo(self, path_arquivo: str) -> str:
        return f'{LOCAL_STORAGE_ROOT_PATH}/{path_arquivo}'
