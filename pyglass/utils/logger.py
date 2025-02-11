import logging
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
from threading import Lock
from rich.logging import RichHandler


class Logger:
    _instance = None
    _lock = Lock()
    _queue = Queue()
    _listener = None

    def __new__(cls, verbose: bool = False, logfile: str = "default.log"):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, verbose: bool = False, logfile: str = "default.log"):
        if self._initialized:  # Prevent re-initialization
            return

        self.verbose = verbose
        self.logfile = logfile
        self._initialized = True

    def get_loggers(self) -> tuple[logging.Logger, logging.Logger]:
        """Returns the file and console loggers."""
        # Lazy loading of loggers
        if not hasattr(self, "console_logger"):
            self._setup_loggers()
        return self.console_logger, self.file_logger

    def _setup_loggers(self) -> None:
        """Creates separate loggers for console and file logging."""
        log_level = logging.DEBUG if self.verbose else logging.INFO
        log_format = "%(levelname)s: %(message)s"

        # Console logger with rich handler
        self.console_logger = logging.getLogger("console_logger")
        self.console_logger.setLevel(log_level)
        self.console_logger.handlers.clear()
        self.console_logger.propagate = False
        # rich_handler = RichHandler(show_time=False, show_path=False, markup=True)
        rich_handler = RichHandler(show_time=False, markup=True)

        self.console_logger.addHandler(rich_handler)

        # File logger with file handler and formatter
        self.file_logger = logging.getLogger("file_logger")
        self.file_logger.setLevel(log_level)
        self.file_logger.handlers.clear()
        self.file_logger.propagate = False
        file_handler = logging.FileHandler(self.logfile)
        file_formatter = logging.Formatter(log_format)
        file_handler.setFormatter(file_formatter)
        self.file_logger.addHandler(file_handler)

        # Set up queue listener for non-blocking logging
        if self._listener is None:
            handler = QueueHandler(self._queue)
            self.console_logger.addHandler(handler)
            self.file_logger.addHandler(handler)

            self._listener = QueueListener(self._queue, rich_handler, file_handler)
            self._listener.start()


if __name__ == "__main__":
    logger_manager = Logger(verbose=True, logfile="app.log")
    CLOG, FLOG = logger_manager.get_loggers()
    CLOG.info("This is a console log message.")
    FLOG.info("This is a file log message.")
