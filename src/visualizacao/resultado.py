import logging

from jinja2 import Environment, FileSystemLoader

from storage import Storage
from models import Processo


class GeraVisualizacao:
    PATH_ARQUIVO: str = '{id_processo}/dados_processo.html'

    def __init__(self, storage: Storage, numero_processo: str) -> None:
        self._storage: Storage = storage
        self._numero_processo: str = numero_processo
        self._looger = logging.getLogger(f"[{__name__}][{self.__class__.__name__}]")

    def gerar_visalizacao(self) -> None:
        self._looger.info('Gerando Visualização dos dados do processo em HTML')
        env = Environment(loader=FileSystemLoader('src/visualizacao/templates'))
        template = env.get_template("processo.html")
        processo: Processo | None = Processo.carregar(
            storage=self._storage, registro_stj=self._numero_processo
        )
        if not processo:
            raise ValueError(f'Não há dados do processo {self._numero_processo}')
        html = template.render(processo=processo).encode()
        path_html = self.PATH_ARQUIVO.format(id_processo=processo.id_processo)
        self._storage.salvar_arquivo(path_arquivo=path_html, content=html)
        path_completo_arquivo = self._storage._obter_path_completo(path_html)
        self._looger.info('Dados em html salvos em %s', path_completo_arquivo)
