import argparse
import logging

from storage import Storage
from crawler_processo import CrawlerProcesso
from visualizacao.resultado import GeraVisualizacao
from parser import NenhumRegistroEncontradoException


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
)

parser = argparse.ArgumentParser(description='Buscador de processos do STJ')
parser.add_argument('--processo')
args = parser.parse_args()
numero_processo = args.processo


if __name__ == '__main__':
    storage = Storage()
    try:
        numero_processo = CrawlerProcesso(storage=storage, numero_processo=numero_processo).buscar_processo()
        GeraVisualizacao(storage=storage, numero_processo=numero_processo).gerar_visalizacao()
    except NenhumRegistroEncontradoException:
        logging.error('Nenhum registro encontrado')
