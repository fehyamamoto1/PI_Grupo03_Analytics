import os
from dataclasses import dataclass
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()

PASSWORD_PLACEHOLDER = "<db_password>"


@dataclass(frozen=True)
class Config:
    data_source: str
    mongo_uri: str
    mongo_db: str
    seed: int

    @property
    def is_mongo(self) -> bool:
        return self.data_source == "mongo"

    @property
    def safe_uri(self) -> str:
        if "@" not in self.mongo_uri:
            return self.mongo_uri
        head, tail = self.mongo_uri.split("@", 1)
        if ":" not in head.split("//", 1)[-1]:
            return self.mongo_uri
        scheme, cred = head.split("//", 1)
        user = cred.split(":", 1)[0]
        return f"{scheme}//{user}:***@{tail}"


def _resolve_uri(uri: str, password: str) -> str:
    if not uri or PASSWORD_PLACEHOLDER not in uri:
        return uri
    if not password:
        return uri
    return uri.replace(PASSWORD_PLACEHOLDER, quote_plus(password))


def load_config() -> Config:
    source = os.getenv("DATA_SOURCE", "seed").strip().lower()
    if source not in ("seed", "mongo"):
        raise ValueError(
            f"DATA_SOURCE invalido: {source!r}. Use 'seed' ou 'mongo'."
        )
    return Config(
        data_source=source,
        mongo_uri=_resolve_uri(
            os.getenv("MONGO_URI", "").strip(),
            os.getenv("MONGO_PASSWORD", "").strip(),
        ),
        mongo_db=os.getenv("MONGO_DB", "PrincipalDB").strip(),
        seed=int(os.getenv("SEED", "42")),
    )
