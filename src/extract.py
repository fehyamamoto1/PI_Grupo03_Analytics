from __future__ import annotations

from .config import PASSWORD_PLACEHOLDER, Config
from .schema import COLLECTIONS

TIMEOUT_MS = 20000


def _diagnose(client, cfg: Config, found: set) -> str:
    linhas = [
        f"O banco '{cfg.mongo_db}' não tem as collections esperadas "
        f"{list(COLLECTIONS)}."
    ]
    linhas.append(
        f"Collections encontradas em '{cfg.mongo_db}': "
        + (", ".join(sorted(found)) if found else "nenhuma")
    )
    try:
        for nome in client.list_database_names():
            if nome in ("admin", "local", "config"):
                continue
            outras = set(client[nome].list_collection_names())
            bate = [c for c in COLLECTIONS if c in outras]
            if bate:
                linhas.append(
                    f"O banco '{nome}' tem {bate} -> ajuste MONGO_DB={nome}"
                )
    except Exception:
        linhas.append("(sem permissao para listar os outros bancos)")
    return "\n".join(linhas)


def from_mongo(cfg: Config) -> dict:
    if not cfg.mongo_uri:
        raise RuntimeError(
            "MONGO_URI vazio. Preencha o .env ou use DATA_SOURCE=seed."
        )
    if PASSWORD_PLACEHOLDER in cfg.mongo_uri:
        raise RuntimeError(
            f"A MONGO_URI ainda tem o placeholder {PASSWORD_PLACEHOLDER}. "
            "Preencha MONGO_PASSWORD no .env com a senha do usuário do Atlas."
        )

    from pymongo import MongoClient
    from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

    client = MongoClient(cfg.mongo_uri, serverSelectionTimeoutMS=TIMEOUT_MS)
    try:
        try:
            db = client[cfg.mongo_db]
            encontradas = set(db.list_collection_names())
        except OperationFailure as exc:
            raise RuntimeError(
                "O Atlas recusou a autenticacao ou o acesso ao banco "
                f"({cfg.safe_uri}): {exc}. Confira usuário, senha e se o IP "
                "atual está liberado em Network Access."
            ) from exc
        except ServerSelectionTimeoutError as exc:
            raise RuntimeError(
                f"Sem resposta do cluster ({cfg.safe_uri}) em "
                f"{TIMEOUT_MS // 1000}s. O cluster pode estar pausado, ou o IP "
                "atual não está liberado em Network Access."
            ) from exc

        if not any(c in encontradas for c in COLLECTIONS):
            raise RuntimeError(_diagnose(client, cfg, encontradas))

        out = {}
        for name in COLLECTIONS:
            docs = list(db[name].find({}))
            for doc in docs:
                doc["_id"] = str(doc["_id"])
            out[name] = docs
        return out
    finally:
        client.close()


def load_raw(cfg: Config) -> dict:
    if cfg.is_mongo:
        return from_mongo(cfg)
    from .seed import generate

    return generate(seed=cfg.seed)
