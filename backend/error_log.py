"""One dated error log for the website: every error, and crashes marked CRITICAL.

`logging_config()` extends uvicorn's own logging settings with a file handler, because
uvicorn applies its settings when it starts and would otherwise drop a handler added
earlier. ERROR and CRITICAL records from the application and from uvicorn go to
`errors.log` in `TRACKER_LOG_DIR` (default: `logs/` in the repository), one file per day,
kept 90 days. Each line starts with the local date, time and UTC offset. Tracebacks are
included; request bodies and local variables never are, so passwords and activation codes
cannot end up here.
"""
import copy
import logging.config
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def log_path():
    return Path(os.environ.get('TRACKER_LOG_DIR') or ROOT / 'logs') / 'errors.log'


def logging_config():
    from uvicorn.config import LOGGING_CONFIG
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    config = copy.deepcopy(LOGGING_CONFIG)
    config['formatters']['errors'] = {
        'format': '%(asctime)s %(levelname)s [%(name)s] %(message)s',
        'datefmt': '%Y-%m-%d %H:%M:%S %z'}
    config['handlers']['errors'] = {
        'class': 'logging.handlers.TimedRotatingFileHandler', 'filename': str(path),
        'when': 'midnight', 'backupCount': 90, 'encoding': 'utf-8',
        'level': 'ERROR', 'formatter': 'errors'}
    # uvicorn.error propagates to uvicorn, so one handler there covers both.
    config['loggers']['uvicorn']['handlers'].append('errors')
    config['loggers'][''] = {'handlers': ['default', 'errors'], 'level': 'WARNING'}
    return config


def configure():
    """For code that logs without uvicorn, such as the systemd exit report."""
    logging.config.dictConfig(logging_config())
