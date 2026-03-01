import json

from abc import ABC
from time import time
from typing import Self, ClassVar

from pydantic import BaseModel

from storage import Storage


class BaseModelPersistente(BaseModel, ABC):
    """Interface base para models persistentes que utilizam Storage.

    Fornece métodos para serializar e deserializar modelos Pydantic
    em arquivos JSON através de um Storage.

    Attributes:
        PATH_ARQUIVO: Nome do arquivo usado para persistir ou obter
            dados do model. Deve ser definido em cada subclasse.
    """

    PATH_ARQUIVO: ClassVar[str]

    def persistir_no_storage(self, storage: Storage) -> None:
        """Serializa e persiste o model no Storage.
        """
        content: bytes = self.model_dump_json().encode()
        storage.salvar_arquivo(path_arquivo=self.PATH_ARQUIVO, content=content)

    @classmethod
    def obter_do_storage(cls, storage: Storage) -> Self | None:
        """Obtém e deserializa o model a partir do Storage.
        """
        arquivo: bytes = storage.obter_arquivo(path_arquivo=cls.PATH_ARQUIVO)
        if not arquivo:
            return None
        return cls(**json.loads(arquivo))


class SessaoSTJ(BaseModelPersistente):
    """Representa uma sessão autenticada no STJ.

    Armazena os dados necessários para manter e verificar
    a validade de uma sessão HTTP com o STJ, com suporte
    a persistência via Storage.
    """

    PATH_ARQUIVO: ClassVar[str] = "dados_sessao.json"

    user_agent: str
    cookies: str
    tempo_de_vida: int  # timestamp Unix

    @property
    def expirou(self) -> bool:
        """Verifica se a sessão está expirada.

        Compara o timestamp atual com o tempo de vida da sessão.

        Returns:
            True se a sessão expirou, False caso contrário.
        """
        timestamp_atual = int(time())
        if timestamp_atual >= self.tempo_de_vida:
            return True
        else:
            return False
