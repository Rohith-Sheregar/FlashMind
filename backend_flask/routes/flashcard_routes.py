from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

try:
    from backend_flask.services import db_service
    from backend_flask.config import DEFAULT_PAGE_SIZE
except ModuleNotFoundError:
    from services import db_service
    from config import DEFAULT_PAGE_SIZE

flashcard_bp = Blueprint('flashcard_bp', __name__)


@flashcard_bp.route('/list-generated', methods=['GET'])
@jwt_required()
def list_generated():
    try:
        current_user = get_jwt_identity()
        limit = int(request.args.get('limit', DEFAULT_PAGE_SIZE))
        records = db_service.list_generated(limit=limit, username=current_user)
        for record in records:
            record.pop('document_text', None)
        return jsonify(records)
    except Exception as e:
        return jsonify({'error': str(e), 'records': []}), 500
