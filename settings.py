import os

GAME_NAME = "Dawn of the Titans"
PROXY_LISTEN_PORTS = [4000]
SERVER_AMP_HOST = 'localhost'
SERVER_AMP_PORT = 4001

USER_IDLE_TIMEOUT = 0

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_PATH, 'src')
LOG_DIR = os.path.join(BASE_PATH, 'log')

SECRET_KEY = 'CHANGE-ME-AND-KEEP-SAFE'

DATABASES = {
    'objects': {
        'NAME': 'dott_objects',
    },
    'accounts': {
        'NAME': 'dott_accounts',
    }
}

# Amazon Web Services credentials.
AWS_ACCESS_KEY_ID = 'XXXXXXXXXXXXXXXXXXXXX'
AWS_SECRET_ACCESS_KEY = 'YYYYYYYYYYYYYYYYYYYYYYYYYYY'
# This needs to be set to one of your Amazon SES verified email addresses.
SERVER_EMAIL_FROM = 'your@email.com'
# The ID of the room or object that new PlayerObjects are created in.
NEW_PLAYER_LOCATION_ID = 1

try:
    from local_settings import *
except ImportError:
    pass