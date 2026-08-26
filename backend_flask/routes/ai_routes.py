import os
import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

try:
    from backend_flask.services import ai_service
    from backend_flask.services.db_service import get_record_by_id, check_generation_limit, increment_generation_count, save_generated
    from backend_flask.config import DAILY_GENERATION_LIMIT
except ModuleNotFoundError:
    from services import ai_service
    from services.db_service import get_record_by_id, check_generation_limit, increment_generation_count, save_generated
    from config import DAILY_GENERATION_LIMIT

logger = logging.getLogger(__name__)
ai_bp = Blueprint('ai_bp', __name__)


def process_ai_request(action_func, field_name=None):
    current_user = get_jwt_identity()

    data = request.get_json()
    record_id = data.get('record_id')
    if not record_id:
        return jsonify({'error': 'record_id is required'}), 400

    record = get_record_by_id(record_id)
    if not record or record.get('created_by') != current_user:
        return jsonify({'error': 'Document not found'}), 404

    force = bool(data.get('force'))
    if field_name and field_name in record and record[field_name] and not force:
        return jsonify({'data': record[field_name]}), 200

    if not check_generation_limit(current_user, limit=DAILY_GENERATION_LIMIT):
        return jsonify({'error': 'You have reached your daily limit. Come back tomorrow!'}), 429

    text = record.get('document_text') or ''
    if not text:
        filepaths = record.get('paths') or ([record.get('path')] if record.get('path') else [])
        existing = [p for p in filepaths if p and os.path.exists(p)]
        if not existing:
            return jsonify({'error': 'The original file is no longer on the server. Please re-upload this document.'}), 410
        text = ai_service.get_document_text(existing)
        if text:
            record['document_text'] = text
            save_generated(record)

    if not text:
        return jsonify({'error': 'Could not extract text from document'}), 422

    try:
        result = action_func(text)
        if field_name:
            record[field_name] = result
            save_generated(record)
            increment_generation_count(current_user)
        return jsonify({'data': result}), 200
    except ValueError as e:
        logger.error(f"ValueError in {field_name}: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error in {field_name}: {e}")
        return jsonify({'error': 'AI generation failed: ' + str(e)}), 500


@ai_bp.route('/generate-quiz', methods=['POST'])
@jwt_required()
def generate_quiz_route():
    return process_ai_request(ai_service.generate_quiz, 'quiz')


@ai_bp.route('/generate-mindmap', methods=['POST'])
@jwt_required()
def generate_mindmap_route():
    return process_ai_request(ai_service.generate_mindmap, 'mindmap')


@ai_bp.route('/extract-topics', methods=['POST'])
@jwt_required()
def extract_topics_route():
    return process_ai_request(ai_service.extract_topics, 'topics')


@ai_bp.route('/generate-flashcards', methods=['POST'])
@jwt_required()
def generate_flashcards_route():
    return process_ai_request(ai_service.generate_flashcards, 'flashcards')
