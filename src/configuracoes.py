from os import environ
from zoneinfo import ZoneInfo


TIME_ZONE = ZoneInfo("America/Sao_Paulo")

LOCAL_STORAGE_ROOT_PATH: str = environ.get('LOCAL_STORAGE_ROOT_PATH', 'local_storage')

FLARESOLVERR_HOST: str = environ.get('FLARESOLVERR_HOST', 'http://localhost:8191')
