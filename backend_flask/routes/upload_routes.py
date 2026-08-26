import os
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename
from flask_jwt_extended import jwt_required, get_jwt_identity

try:
    from backend_flask import config as cfg
    from backend_flask.services import file_service, db_service, ai_service
except ModuleNotFoundError:
    import config as cfg
    from services import file_service, db_service, ai_service

logger = logging.getLogger(__name__)
upload_bp = Blueprint('upload_bp', __name__)

ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx", "txt", "md", "markdown", "png", "jpg", "jpeg", "webp"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_TOTAL_CHARS = getattr(cfg, 'MAX_TOTAL_CHARS', 5_000_000)
UPLOAD_FOLDER = getattr(cfg, 'UPLOAD_DIR', 'uploads')
FILE_SIZE_LIMIT = getattr(cfg, 'MAX_UPLOAD_SIZE_BYTES', 10 * 1024 * 1024)
PDF_FILE_SIZE_LIMIT = getattr(cfg, 'MAX_PDF_UPLOAD_SIZE_BYTES', 10 * 1024 * 1024)
MAX_FILES_PER_DECK = getattr(cfg, 'MAX_FILES_PER_DECK', 20)


def _ext(filename: str) -> str:
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()


def _allowed(filename: str) -> bool:
    return _ext(filename) in ALLOWED_EXTENSIONS


def _size_limit(filename: str) -> int:
    return PDF_FILE_SIZE_LIMIT if _ext(filename) == 'pdf' else FILE_SIZE_LIMIT


def _format_bytes(n: int) -> str:
    return f"{n / (1024 * 1024):.0f} MB"


def _file_size(storage_file) -> int:
    storage_file.stream.seek(0, os.SEEK_END)
    size = storage_file.stream.tell()
    storage_file.stream.seek(0)
    return size


def _save_file(storage_file) -> Tuple[str, str]:
    filename = secure_filename(storage_file.filename)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filepath = os.path.join(UPLOAD_FOLDER, f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{filename}")
    storage_file.save(filepath)
    return filename, filepath


def _collect_files() -> List[Any]:
    files = request.files.getlist('files') or request.files.getlist('file')
    return [f for f in files if f and f.filename]


def _deck_title(files: List[Any], form: Any) -> str:
    title = (form.get('deck_name') or '').strip()
    if title:
        return secure_filename(title) or title

    names = [secure_filename(f.filename) for f in files]
    if len(names) == 1:
        return names[0]

    stem = (names[0] or 'uploaded-files').rsplit('.', 1)[0]
    if all(_ext(n) in IMAGE_EXTENSIONS for n in names):
        return f"{stem} image deck ({len(names)} images)"
    return f"{stem} deck ({len(names)} files)"


def _paths_for(record: Dict[str, Any]) -> List[str]:
    paths = record.get('paths')
    if isinstance(paths, list) and paths:
        return [p for p in paths if p]
    path = record.get('path')
    return [path] if path else []


def _extract_chunks(paths: List[str], filenames: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    for idx, filepath in enumerate(paths):
        source = filenames[idx] if filenames and idx < len(filenames) else os.path.basename(filepath)
        for chunk in file_service.extract_text_chunks(filepath, max_chunk_chars=2000, overlap_chars=200):
            chunks.append({**chunk, 'source_file': source, 'source_index': idx})
    return chunks


@upload_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload() -> Any:
    storage_files = _collect_files()
    if not storage_files:
        return jsonify({'error': 'missing file field'}), 400
    if len(storage_files) > MAX_FILES_PER_DECK:
        return jsonify({'error': f'upload up to {MAX_FILES_PER_DECK} files per deck'}), 400

    for f in storage_files:
        if not f.filename:
            return jsonify({'error': 'empty filename'}), 400
        if not _allowed(f.filename):
            return jsonify({'error': f'unsupported file type: {f.filename}'}), 415

    form = request.form or {}
    try:
        auto_approve = str(form.get('auto_approve', 'false')).lower() in ('1', 'true', 'yes')
    except Exception:
        return jsonify({'error': 'invalid parameters'}), 400

    current_user = get_jwt_identity()
    created_by = form.get('created_by') or current_user
    deck_title = _deck_title(storage_files, form)

    if db_service.check_duplicate(deck_title, created_by):
        return jsonify({'error': 'Duplicate document upload not allowed.'}), 400

    total_size = 0
    for f in storage_files:
        size = _file_size(f)
        total_size += size
        limit = _size_limit(f.filename)
        if size > limit:
            return jsonify({'error': f'{f.filename} is too large; limit is {_format_bytes(limit)}'}), 413

    filenames: List[str] = []
    filepaths: List[str] = []
    try:
        for f in storage_files:
            name, path = _save_file(f)
            filenames.append(name)
            filepaths.append(path)
    except Exception as e:
        logger.exception("Failed to save file: %s", e)
        return jsonify({'error': 'failed to save file'}), 500

    try:
        chunks = _extract_chunks(filepaths, filenames)
    except Exception as e:
        logger.exception("Text extraction failed: %s", e)
        for path in filepaths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        return jsonify({'error': 'failed to extract text from file'}), 500

    if not chunks:
        return jsonify({'error': 'no text could be extracted from the document'}), 400

    document_text = "\n\n".join(c.get('text', '') for c in chunks if c.get('text'))
    if len(document_text) > MAX_TOTAL_CHARS:
        return jsonify({'error': 'document too large; reduce size or split into smaller files'}), 413

    record: Dict[str, Any] = {
        'source_file': deck_title,
        'source_files': filenames,
        'path': filepaths[0],
        'paths': filepaths,
        'file_count': len(filepaths),
        'total_upload_size': total_size,
        'document_text': document_text,
        'num_chunks': len(chunks),
        'flashcards': [],
        'auto_approved': auto_approve,
        'created_by': created_by,
        'model_version': 'openrouter_gpt-4o-mini',
        'stats': {'flashcards_generated': 0, 'chunks_processed': len(chunks)}
    }

    try:
        saved_id = db_service.save_generated(record)
        if auto_approve and hasattr(db_service, 'mark_approved'):
            db_service.mark_approved(saved_id)
    except Exception as e:
        logger.exception("Failed to save record: %s", e)
        return jsonify({'error': 'failed to save record'}), 500

    return jsonify({
        'status': 'ok',
        'record_id': str(saved_id),
        'flashcards': [],
        'total_flashcards': 0,
        'files_uploaded': len(filepaths)
    }), 200


@upload_bp.route('/list', methods=['GET'])
@jwt_required()
def list_records() -> Any:
    current_user = get_jwt_identity()
    records = db_service.list_generated(limit=50, username=current_user)
    for r in records:
        r.pop('document_text', None)
        if r.get('flashcards'):
            r['flashcards'] = r['flashcards'][:1]
    return jsonify(records)


@upload_bp.route('/documents/<record_id>', methods=['DELETE'])
@jwt_required()
def delete_document(record_id: str) -> Any:
    current_user = get_jwt_identity()
    success = db_service.delete_record(record_id, username=current_user)
    if success:
        return jsonify({'message': 'Document deleted successfully'})
    return jsonify({'error': 'Failed to delete document or unauthorized'}), 400


@upload_bp.route('/regenerate/<record_id>', methods=['POST'])
@jwt_required()
def regenerate(record_id: str):
    record = db_service.get_record_by_id(record_id)
    if not record:
        return jsonify({'error': 'record not found'}), 404

    text = record.get('document_text') or ''
    if not text:
        paths = _paths_for(record)
        if not paths or any(not os.path.exists(p) for p in paths):
            return jsonify({'error': 'original file not found; please re-upload this document'}), 410
        try:
            chunks = _extract_chunks(paths, record.get('source_files'))
        except Exception as e:
            logger.exception("Text extraction failed: %s", e)
            return jsonify({'error': 'failed to extract text from file'}), 500
        text = "\n\n".join(c.get('text', '') for c in chunks)
        record['document_text'] = text

    try:
        flashcards = ai_service.generate_flashcards(text)
    except Exception as e:
        logger.exception("Flashcard generation failed: %s", e)
        return jsonify({'error': 'AI generation failed'}), 500

    record['flashcards'] = flashcards
    record['stats']['flashcards_generated'] = len(flashcards)
    db_service.save_generated(record)

    return jsonify({'status': 'ok', 'flashcards': flashcards}), 200
