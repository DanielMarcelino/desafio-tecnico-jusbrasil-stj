import json

from abc import ABC
from datetime import datetime
from time import time
from typing import Self, ClassVar

from pydantic import BaseModel, field_serializer, field_validator

from configuracoes import TIME_ZONE
from storage import Storage


class BaseModelPersistente(BaseModel, ABC):
    """Interface base para models persistentes que utilizam Storage.

    Fornece métodos para serializar e deserializar modelos Pydantic
    em arquivos JSON através de um Storage.

    Attributes:
        PATH_ARQUIVO (ClassVar[str]): Nome do arquivo usado para persistir ou obter
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


class SolucaoAntigate(BaseModelPersistente):
    """Representa uma sessão autenticada através da solução de um CAPTCHA.

    Armazena os dados necessários para manter e verificar
    a validade de uma sulução de CAPTCHA, com suporte
    a persistência via Storage.
    """

    PATH_ARQUIVO: ClassVar[str] = "dados_solucao_turnstile.json"

    user_agent: str
    cookies: str
    tempo_de_vida: int  # timestamp Unix

    @property
    def expirou(self) -> bool:
        """Verifica se a sessão está expirada.

        Compara o timestamp atual com o tempo de vida da solução.

        Returns:
            True se a sessão expirou, False caso contrário.
        """
        timestamp_atual = int(time())
        if timestamp_atual >= self.tempo_de_vida:
            return True
        else:
            return False


class Documento(BaseModel):
    """Representa um documento anexado a um processo judicial.

    Attributes:
        identificador_unico: Identificador único do documento no sistema de origem.
        descricao: Descrição ou nome do documento. Pode ser nulo.
        link: URL para acesso ao documento no sistema de origem.
        path_arquivo: Caminho local do arquivo baixado. Nulo enquanto não baixado.
    """

    identificador_unico: str
    descricao: str | None
    link: str
    path_arquivo: str | None = None


class Movimento(BaseModel):
    """Representa um movimento (andamento) registrado no processo judicial.

    A igualdade e o hash são calculados com base em `numero`, `data` e `descricao`,
    permitindo uso em conjuntos e deduplicação de movimentos.

    Attributes:
        data: Data e hora do movimento, normalizada para o fuso horário configurado.
        descricao: Texto descritivo do movimento.
        documentos: Lista de documentos associados ao movimento.
    """

    data: datetime
    descricao: str
    documentos: list[Documento]

    def __eq__(self, value: object) -> bool:
        """Compara dois movimentos por data e descricao."""
        if isinstance(value, Movimento):
            return (self.data, self.descricao) == (
                value.data,
                value.descricao,
            )
        return super().__eq__(value)

    def __hash__(self) -> int:
        """Hash baseado na data e descricao para uso em sets e dicts."""
        return hash((self.data, self.descricao))

    @field_serializer("data", when_used="json")
    def _serialize_data(self, v: datetime) -> str:
        """Serializa o campo `data` como string ISO 8601 ao exportar para JSON."""
        return v.isoformat()

    @field_validator("data", mode="after")
    @classmethod
    def datetime_as_timezone(cls, v: datetime) -> datetime:
        """Converte `data` para o fuso horário configurado em TIME_ZONE."""
        if isinstance(v, datetime):
            return v.astimezone(TIME_ZONE)
        return v


class Pauta(BaseModel):
    """Representa uma pauta de julgamento associada ao processo.

    Attributes:
        data_sessao: Data e hora da sessão de julgamento, normalizada para TIME_ZONE.
        orgao_julgador: Nome do órgão julgador responsável pela sessão.
        documento: Documento relacionado à pauta.
    """

    data_sessao: datetime
    orgao_julgador: str
    documento: Documento

    @field_serializer("data_sessao", when_used="json")
    def _serialize_datetime(self, v: datetime) -> str:
        """Serializa `data_sessao` como string ISO 8601 ao exportar para JSON."""
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    @field_validator("data_sessao", mode="after")
    @classmethod
    def datetime_as_timezone(cls, v: datetime) -> datetime:
        """Converte `data_sessao` para o fuso horário configurado em TIME_ZONE."""
        if isinstance(v, datetime):
            return v.astimezone(TIME_ZONE)
        return v


class Peticao(BaseModel):
    """Representa uma petição protocolada no processo.

    Attributes:
        numero_protocolo: Número de protocolo da petição.
        data_protocolo: Data e hora do protocolo, normalizada para TIME_ZONE.
        tipo: Tipo ou categoria da petição.
        data_processamento: Data e hora em que a petição foi processada pelo sistema.
        peticionario: Nome do peticionário que protocolou o documento.
    """

    numero_protocolo: str
    data_protocolo: datetime
    tipo: str
    data_processamento: datetime
    peticionario: str

    @field_serializer("data_protocolo", "data_processamento", when_used="json")
    def _serialize_datetime(self, v: datetime) -> str:
        """Serializa campos datetime como string ISO 8601 ao exportar para JSON."""
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    @field_validator("data_protocolo", "data_processamento", mode="after")
    @classmethod
    def datetime_as_timezone(cls, v: datetime) -> datetime:
        """Converte os campos datetime para o fuso horário configurado em TIME_ZONE."""
        if isinstance(v, datetime):
            return v.astimezone(TIME_ZONE)
        return v


class Parte(BaseModel):
    """Representa uma parte envolvida no processo judicial.

    Attributes:
        designacao: Papel da parte no processo (ex: Autor, Réu, Recorrente).
        nome: Nome completo da parte.
    """

    designacao: str
    nome: str


class Advogado(BaseModel):
    """Representa um advogado vinculado ao processo.

    Attributes:
        nome: Nome completo do advogado.
        oab: Número de inscrição na OAB, incluindo seccional (ex: SP123456).
    """

    nome: str
    oab: str


class DetalhesProcesso(BaseModel):
    """Contém os metadados e informações estruturais do processo judicial.

    Attributes:
        numero_stj: Número do processo no STJ. Nulo se não aplicável.
        registro_stj: Número de registro interno no STJ.
        numero_cnj: Número único do processo no formato CNJ. Nulo se não disponível.
        classe: Classe processual (ex: Recurso Especial, Habeas Corpus).
        localizacao: Localização física ou eletrônica atual do processo.
        tipo: Tipo do processo.
        autuacao: Data de autuação do processo, normalizada para TIME_ZONE.
        relator: Nome do ministro/desembargador relator.
        ramo_do_direito: Ramo do direito (ex: Direito Civil, Direito Penal).
        assuntos: Lista de assuntos classificados no processo.
        tribunal_origem: Nome do tribunal de origem.
        volume_apenso: Informação sobre volumes e apensos do processo.
        numeros_de_origem: Lista de números do processo nos tribunais de origem.
    """

    numero_stj: str | None
    registro_stj: str
    numero_cnj: str | None
    classe: str | None
    localizacao: str | None
    tipo: str | None
    autuacao: datetime | None
    relator: str | None
    ramo_do_direito: str | None
    assuntos: list[str]
    tribunal_origem: str | None
    volume_apenso: str | None
    numeros_de_origem: list[str]

    @field_serializer("autuacao", when_used="json")
    def _serialize_data(self, v: datetime) -> str:
        """Serializa `autuacao` como string ISO 8601 ao exportar para JSON."""
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    @field_validator("autuacao", mode="after")
    @classmethod
    def datetime_as_timezone(cls, v: datetime) -> datetime:
        """Converte `autuacao` para o fuso horário configurado em TIME_ZONE."""
        if isinstance(v, datetime):
            return v.astimezone(TIME_ZONE)
        return v


class DadosProcesso(BaseModel):
    """Agrega todos os dados de um processo judicial em uma única estrutura.

    É o modelo raiz retornado pelo scraper, reunindo detalhes, partes,
    advogados, petições, pautas e movimentos do processo.

    Attributes:
        detalhes: Metadados e informações estruturais do processo.
        partes: Lista das partes envolvidas no processo.
        advogados: Lista dos advogados vinculados ao processo.
        peticoes: Lista das petições protocoladas.
        pautas: Lista das pautas de julgamento.
        movimentos: Lista dos movimentos/andamentos processuais.
        ultima_atualizacao: Data e hora da última atualização dos dados, normalizada para TIME_ZONE.
    """

    detalhes: DetalhesProcesso
    partes: list[Parte]
    advogados: list[Advogado]
    peticoes: list[Peticao]
    pautas: list[Pauta]
    movimentos: list[Movimento]
    ultima_atualizacao: datetime

    @field_serializer("ultima_atualizacao", when_used="json")
    def _serialize_data(self, v: datetime) -> str:
        """Serializa `ultima_atualizacao` como string ISO 8601 ao exportar para JSON."""
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    @field_validator("ultima_atualizacao", mode="after")
    @classmethod
    def datetime_as_timezone(cls, v: datetime) -> datetime:
        """Converte `ultima_atualizacao` para o fuso horário configurado em TIME_ZONE."""
        if isinstance(v, datetime):
            return v.astimezone(TIME_ZONE)
        return v
