"""
Centralized logging configuration for the posture detection system.
"""

import logging
import sys
from pathlib import Path


class PostureLogger:
    """Centralized logging configuration for posture detection system"""

    def __init__(self, log_level: str = "INFO", log_to_file: bool = True):
        self.log_level = log_level.upper()
        self.log_to_file = log_to_file
        self.setup_logging()

    def setup_logging(self):
        """Setup logging configuration"""
        # Create logger
        self.logger = logging.getLogger("posture_detection")
        self.logger.setLevel(getattr(logging, self.log_level, logging.INFO))

        # Clear any existing handlers
        self.logger.handlers.clear()

        # Create formatters
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
        )

        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, self.log_level, logging.INFO))
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # File handler (if enabled)
        if self.log_to_file:
            log_dir = Path(__file__).parent / "logs"
            log_dir.mkdir(exist_ok=True)

            file_handler = logging.FileHandler(log_dir / "posture_detection.log")
            file_handler.setLevel(logging.DEBUG)  # Always log everything to file
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

    def get_logger(self, name: str = None) -> logging.Logger:
        """Get a logger instance"""
        if name:
            return logging.getLogger(f"posture_detection.{name}")
        return self.logger

    def set_level(self, level: str):
        """Change logging level at runtime"""
        self.log_level = level.upper()
        log_level_int = getattr(logging, self.log_level, logging.INFO)

        self.logger.setLevel(log_level_int)
        for handler in self.logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(
                handler, logging.FileHandler
            ):
                handler.setLevel(log_level_int)


# Global logger instance
_posture_logger = None


def get_logger(name: str = None, log_level: str = "INFO") -> logging.Logger:
    """Get a configured logger instance"""
    global _posture_logger

    if _posture_logger is None:
        _posture_logger = PostureLogger(log_level=log_level)

    return _posture_logger.get_logger(name)


def set_log_level(level: str):
    """Set logging level globally"""
    global _posture_logger

    if _posture_logger is None:
        _posture_logger = PostureLogger(log_level=level)
    else:
        _posture_logger.set_level(level)
