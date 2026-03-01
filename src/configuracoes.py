from os import environ


LOCAL_STORAGE_ROOT_PATH: str = environ.get('LOCAL_STORAGE_ROOT_PATH', 'local_storage')

FLARESOLVERR_HOST: str = environ.get('FLARESOLVERR_HOST', 'http://localhost:8191')

PROXY_URL: str = environ.get('PROXY_URL', '')
