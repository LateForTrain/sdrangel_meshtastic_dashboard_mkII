from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class Config:
    udp_host: str = os.getenv("UDP_HOST", "0.0.0.0")
    udp_port: int = int(os.getenv("UDP_PORT", "9999"))
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    db_dir: str = os.getenv("DB_DIR", "./data")
    db_name: str = os.getenv("DB_NAME", "app.db")
    debug_active: bool = os.getenv("DEBUG_ACTIVE", "False")
    debug_log: str = os.getenv("DEBUG_LOG","debug.json")
    mesh_key: str = os.getenv("MESH_KEY", "1PG7OiApB1nwvP+rz05pAQ==")

config = Config()