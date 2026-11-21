from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    name: str = "Aegis AI"
    version: str = "0.2.0"


settings = Settings()
