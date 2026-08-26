import os
import json
import datetime
import logging
from pathlib import Path

try:
    from backend_flask.config import (
        MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION,
        GENERATED_DIR, ENABLE_FILE_DB, MONGO_SERVER_SELECTION_TIMEOUT_MS,
    )
except ModuleNotFoundError:
    from config import (
        MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION,
        GENERATED_DIR, ENABLE_FILE_DB, MONGO_SERVER_SELECTION_TIMEOUT_MS,
    )

logger = logging.getLogger(__name__)

DB_FILE = Path(GENERATED_DIR) / 'flashcard_records.jsonl'

_mongo_client = None
_mongo_available = False

try:
    from pymongo import MongoClient
    _mongo_available = True
except Exception:
    pass


def get_mongo_client():
    global _mongo_client
    if not _mongo_available:
        raise RuntimeError('pymongo not available')
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=MONGO_SERVER_SELECTION_TIMEOUT_MS)
    return _mongo_client


def check_duplicate(filename: str, username: str) -> bool:
    if not _mongo_available:
        return False
    try:
        col = get_mongo_client()[MONGO_DB_NAME][MONGO_COLLECTION]
        record = col.find_one({'source_file': filename, 'created_by': username})
        if not record:
            return False
        if record.get('document_text'):
            return True
        paths = record.get('paths') or ([record.get('path')] if record.get('path') else [])
        return any(p and os.path.exists(p) for p in paths)
    except Exception:
        return False


def delete_record(record_id: str, username: str) -> bool:
    if not _mongo_available:
        return False
    from bson.objectid import ObjectId
    try:
        col = get_mongo_client()[MONGO_DB_NAME][MONGO_COLLECTION]
        record = col.find_one({'_id': ObjectId(record_id)})
        if not record or record.get('created_by') != username:
            return False
        paths = record.get('paths') or ([record.get('path')] if record.get('path') else [])
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"Could not delete file {path}: {e}")
        col.delete_one({'_id': ObjectId(record_id)})
        return True
    except Exception as e:
        logger.error(f"Error deleting record: {e}")
        return False


def get_record_by_id(record_id: str):
    if not _mongo_available:
        return None
    from bson.objectid import ObjectId
    try:
        col = get_mongo_client()[MONGO_DB_NAME][MONGO_COLLECTION]
        return col.find_one({'_id': ObjectId(record_id)})
    except Exception as e:
        logger.error(f"Error fetching record: {e}")
        return None


def get_user_generation_count(username: str) -> int:
    """Return how many generations the user has used TODAY. Resets to 0 after midnight."""
    if not _mongo_available:
        return 0
    try:
        col = get_mongo_client()[MONGO_DB_NAME]['user_limits']
        doc = col.find_one({'username': username})
        today = datetime.date.today().isoformat()
        if not doc or doc.get('last_reset_date') != today:
            # New day — reset in DB so subsequent reads are consistent
            col.update_one(
                {'username': username},
                {'$set': {'generations': 0, 'last_reset_date': today}},
                upsert=True
            )
            return 0
        return doc.get('generations', 0)
    except Exception as e:
        logger.error(f"Error getting generation count: {e}")
        return 0


def check_generation_limit(username: str, limit: int = 5) -> bool:
    if not _mongo_available:
        return True
    try:
        col = get_mongo_client()[MONGO_DB_NAME]['user_limits']
        doc = col.find_one({'username': username})
        today = datetime.date.today().isoformat()
        count = doc.get('generations', 0) if doc and doc.get('last_reset_date') == today else 0
        return count < limit
    except Exception as e:
        logger.error(f"Error checking limit: {e}")
        return True


def increment_generation_count(username: str):
    if not _mongo_available:
        return
    try:
        col = get_mongo_client()[MONGO_DB_NAME]['user_limits']
        today = datetime.date.today().isoformat()
        doc = col.find_one({'username': username})
        if doc and doc.get('last_reset_date') == today:
            update = {'$inc': {'generations': 1}, '$set': {'last_reset_date': today}}
        else:
            update = {'$set': {'generations': 1, 'last_reset_date': today}}
        col.update_one({'username': username}, update, upsert=True)
    except Exception as e:
        logger.error(f"Error incrementing count: {e}")


def _save_mongo(record: dict):
    col = get_mongo_client()[MONGO_DB_NAME][MONGO_COLLECTION]
    if '_id' in record:
        col.replace_one({'_id': record['_id']}, record, upsert=True)
        return str(record['_id'])
    res = col.insert_one(record)
    return str(res.inserted_id)


def _save_file(record: dict):
    if not ENABLE_FILE_DB:
        return None
    os.makedirs(Path(GENERATED_DIR), exist_ok=True)
    with open(DB_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    return str(DB_FILE)


def save_generated(record: dict):
    rec = dict(record)
    rec.setdefault('created_at', datetime.datetime.utcnow())
    if _mongo_available:
        try:
            return _save_mongo(rec)
        except Exception as e:
            if ENABLE_FILE_DB:
                logger.warning(f"Mongo save failed, falling back to file: {e}")
                return _save_file(rec)
            logger.warning("Mongo save failed and file DB is disabled.")
            return None
    if ENABLE_FILE_DB:
        return _save_file(rec)
    return None


def _list_mongo(limit: int, username: str = None):
    col = get_mongo_client()[MONGO_DB_NAME][MONGO_COLLECTION]
    query = {'created_by': username} if username else {}
    docs = list(col.find(query).sort('created_at', -1).limit(limit))
    for d in docs:
        d['_id'] = str(d['_id'])
        if 'created_at' in d:
            try:
                d['created_at'] = d['created_at'].isoformat()
            except Exception:
                d['created_at'] = str(d['created_at'])
    return docs


def _list_file(limit: int, username: str = None):
    if not ENABLE_FILE_DB or not DB_FILE.exists():
        return []
    out = []
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        for line in reversed(list(f)):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if username and obj.get('created_by') != username:
                    continue
                out.append(obj)
                if len(out) >= limit:
                    break
            except Exception:
                continue
    return out


def list_generated(limit: int = 100, username: str = None):
    if _mongo_available:
        try:
            return _list_mongo(limit=limit, username=username)
        except Exception as e:
            if ENABLE_FILE_DB:
                logger.warning(f"Mongo list failed, falling back to file: {e}")
                return _list_file(limit=limit, username=username)
            raise
    return _list_file(limit=limit, username=username)
