"""Handel the application configuration"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import tomllib
 
 
def _load_toml(path: str | Path = "config.toml") -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)
 
 
@dataclass
class Config:
    test_state:   bool 
    udp_host:     str  
    udp_port:     int  
    api_host:     str  
    api_port:     int  
    log_level:    str  
    db_dir:       str  
    db_name:      str  
    debug_active: bool 
    debug_log:    str  
    mesh_key:     str  
 
    @classmethod
    def from_toml(cls, path: str | Path = "config.toml") -> Config:
        t = _load_toml(path)
        return cls(
            test_state  = t["test"]["state"],
            udp_host     = t["udp"]["host"],
            udp_port     = t["udp"]["port"],
            api_host     = t["api"]["host"],
            api_port     = t["api"]["port"],
            log_level    = t["logging"]["level"],
            db_dir       = t["database"]["dir"],
            db_name      = t["database"]["name"],
            debug_active = t["debug"]["active"],
            debug_log    = t["debug"]["log"],
            mesh_key     = t["mesh"]["key"],
        )
 
 
config = Config.from_toml()