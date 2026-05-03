from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class Config:
    udp_host: str = os.getenv("UDP_HOST", "0.0.0.0")
    udp_port: int = int(os.getenv("UDP_PORT", "9999"))          # Common for SDRangel Meshtastic
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    db_path: str = os.getenv("DB_PATH", "data/meshtastic.db.json")


config = Config()