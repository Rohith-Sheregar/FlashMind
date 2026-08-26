"""AI generation service — calls OpenRouter for flashcards, quiz, mindmap, and topics."""
import os
import json
import logging
from openai import OpenAI

try:
    from backend_flask.config import OPENROUTER_API_KEY
    from backend_flask.services.rag_service import condense_text as _rag_condense
except ModuleNotFoundError:
    from config import OPENROUTER_API_KEY
    from services.rag_service import condense_text as _rag_condense

logger = logging.getLogger(__name__)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY or "DUMMY_KEY",
)

MIN_FLASHCARDS = 20
MAX_FLASHCARDS = 50
MIN_QUIZ_QUESTIONS = 20
MAX_QUIZ_QUESTIONS = 35


def _word_count(text: str) -> int:
    return len((text or "").split())


def _target_flashcard_count(text: str, requested_max: int = None) -> int:
    if requested_max:
        return max(1, min(int(requested_max), MAX_FLASHCARDS))
    words = _word_count(text)
    if words < 1200:
        return MIN_FLASHCARDS
    if words < 3000:
        return 30
    if words < 7000:
        return 40
    return MAX_FLASHCARDS


def _target_quiz_count(text: str) -> int:
    words = _word_count(text)
    if words < 2500:
        return MIN_QUIZ_QUESTIONS
    if words < 7000:
        return 25
    return MAX_QUIZ_QUESTIONS


def _target_topic_words(text: str) -> int:
    words = _word_count(text)
    if words < 1200:
        return 200
    if words < 3500:
        return 280
    if words < 9000:
        return 350
    return 400


def get_document_text(filepath) -> str:
    """Extract text from a file path (or list of paths) using file_service."""
    try:
        from backend_flask.services import file_service
    except ModuleNotFoundError:
        import services.file_service as file_service

    if isinstance(filepath, (list, tuple)):
        parts = []
        for idx, single_path in enumerate(filepath, start=1):
            extracted = get_document_text(single_path)
            if extracted:
                parts.append(f"Source {idx}: {single_path}\n{extracted}")
        return "\n\n".join(parts)

    try:
        chunks = file_service.extract_text_chunks(filepath, max_chunk_chars=4000, overlap_chars=0)
        return "\n\n".join(chunk.get("text", "") for chunk in chunks)
    except Exception as e:
        logger.error(f"Failed to extract text from {filepath}: {e}")
        return ""


def _get_rag_context(text: str, max_output_chars: int = 15000) -> str:
    """Condense text via the RAG service (HF API or fallback truncation)."""
    try:
        return _rag_condense(text, max_output_chars=max_output_chars)
    except Exception as e:
        logger.warning(f"RAG condensation failed, falling back to truncation: {e}")
        return text[:max_output_chars]


def call_openrouter(system_prompt: str, user_prompt: str, max_tokens: int = None) -> str:
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not configured.")
    kwargs = {"max_tokens": max_tokens} if max_tokens else {}
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            **kwargs,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenRouter API call failed: {e}")
        raise


def _strip_json_fences(text: str) -> str:
    if "```json" in text:
        return text.split("```json")[1].split("```")[0].strip()
    if "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text


def generate_quiz(text: str) -> list:
    question_count = _target_quiz_count(text)
    system_prompt = (
        "You are an expert educator. Based on the provided document text, "
        f"generate exactly {question_count} multiple-choice quiz questions testing the most important concepts. "
        "For very short documents, still produce 20 useful questions by varying recall, application, and reasoning questions without inventing facts. "
        "STRICTLY IGNORE administrative boilerplate (Vision, Mission, Program Outcomes, Course Objectives, Table of Contents, College info). Focus ONLY on educational subject matter.\n"
        "Respond ONLY with a valid JSON array. Each object must have: "
        "'question' (str), 'options' (list of 4 str), 'correct_index' (int 0-3), 'explanation' (str)."
    )
    rag_text = _get_rag_context(text, max_output_chars=26000)
    response_text = _strip_json_fences(
        call_openrouter(system_prompt, f"Document Text:\n{rag_text}", max_tokens=10000)
    )
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse quiz JSON: {e}\nResponse: {response_text}")
        raise ValueError("Failed to generate valid quiz format.")


def generate_mindmap(text: str) -> str:
    system_prompt = (
        "You are an expert educator and visual designer. Based on the provided document text, "
        "create a highly detailed and memorable Mermaid.js mindmap summarizing the key concepts.\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Start your response with exactly: `mindmap` on the first line.\n"
        "2. The root node must be on the next line, indented by 2 spaces (e.g., `  root((📚 Subject Title))`)\n"
        "3. ALL subsequent branches MUST use ONLY indentation (spaces). DO NOT USE ARROWS (`-->` or `-.->`).\n"
        "4. Keep node text extremely concise (2-5 words max). Include relevant emojis.\n"
        "5. Do NOT include markdown wrappers like ```mermaid. Output raw code only.\n"
        "6. STRICTLY IGNORE administrative boilerplate. Focus ONLY on subject matter.\n"
    )
    rag_text = _get_rag_context(text)
    response_text = call_openrouter(system_prompt, f"Document Text:\n{rag_text}")
    if "```mermaid" in response_text:
        response_text = response_text.split("```mermaid")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()
    return response_text


def extract_topics(text: str) -> str:
    target_words = _target_topic_words(text)
    system_prompt = (
        "You are an expert at summarizing documents. Based on the provided document text, "
        "extract the most important concepts/topics. "
        f"Write about {target_words} words total, scaling detail to the document size. "
        "STRICTLY IGNORE administrative boilerplate (Vision, Mission, Program Outcomes, Table of Contents, College info). Focus ONLY on educational subject matter.\n"
        "Return polished Markdown with clear section headings, concise bullets, bolded key terms, and short explanations."
    )
    rag_text = _get_rag_context(text, max_output_chars=26000)
    return call_openrouter(system_prompt, f"Document Text:\n{rag_text}", max_tokens=2500)


def generate_flashcards(text: str, max_q: int = None) -> list:
    """Generate deep-concept flashcards using OpenRouter."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not configured.")
    target_count = _target_flashcard_count(text, max_q)
    system_prompt = (
        "You are an expert cognitive psychologist and educator. Based on the provided document text, "
        f"create exactly {target_count} highly significant flashcards covering the strongest concepts, mechanisms, or principles. "
        "CRITICAL INSTRUCTIONS: "
        "- Do NOT ask trivial or surface-level questions. "
        "- Focus on 'Why' and 'How' questions that test deep comprehension. "
        "- Keep answers concise but complete enough for revision. "
        "- STRICTLY IGNORE administrative boilerplate. Focus ONLY on educational material. "
        "- Format your response ONLY as a valid JSON array of objects with 'question' (string) and 'answer' (string)."
    )
    try:
        rag_text = _get_rag_context(text, max_output_chars=30000)
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Document Text:\n{rag_text}"},
            ],
            temperature=0.4,
            max_tokens=12000,
        )
        response_text = _strip_json_fences(response.choices[0].message.content)
        return json.loads(response_text)
    except Exception as e:
        logger.error(f"Failed to generate flashcards: {e}")
        return []
