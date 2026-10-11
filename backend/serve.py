"""Production entry point: `python -m backend.serve`, run by the systemd service.

It configures the error log, then runs the website. If the server stops because of an
error, the cause is written as CRITICAL and the process exits non-zero, so systemd
restarts it. `python -m backend.serve --report-exit` is systemd's ExecStopPost: it
records a CRITICAL line when the server died in a way Python could not log (killed,
out of memory), using the result systemd passes in its environment.
"""
import logging.config
import os
import sys

from backend.error_log import configure, logging_config

# Exit status after a crash this module has already logged; ExecStopPost skips it.
LOGGED_CRASH = 70
logger = logging.getLogger('tracker.server')


def serve():
    config = logging_config()
    logging.config.dictConfig(config)
    import uvicorn
    host = os.environ.get('TRACKER_HOST', '127.0.0.1')
    port = int(os.environ.get('TRACKER_PORT', '8000'))
    try:
        uvicorn.run('main:app', host=host, port=port, proxy_headers=True, log_config=config)
    except SystemExit as exc:
        if exc.code not in (0, None):
            # uvicorn exits this way when start-up fails, e.g. the database is unreachable.
            logger.critical('Server stopped: start-up failed (exit status %s)', exc.code)
            sys.exit(LOGGED_CRASH)
        raise
    except BaseException:
        logger.critical('Server crashed', exc_info=True)
        sys.exit(LOGGED_CRASH)


def report_exit():
    configure()
    result = os.environ.get('SERVICE_RESULT', 'unknown')
    status = os.environ.get('EXIT_STATUS', '')
    if result != 'success' and status != str(LOGGED_CRASH):
        logger.critical('Server stopped unexpectedly (systemd result %s, status %s); restarting',
                        result, status or 'unknown')


if __name__ == '__main__':
    report_exit() if '--report-exit' in sys.argv else serve()
