"""Document condensation service using HuggingFace Inference API for embeddings.

Pipeline:
  1. Split document into overlapping chunks with boilerplate filtering.
  2. Call the HuggingFace Inference API to get embeddings for each chunk.
  3. Use greedy max-diversity selection to pick the most representative and
     varied chunks (covers beginning, middle, and end of the document).
  4. Fall back to evenly-spaced truncation if HF API is unavailable or the
     token is not configured.

No local ML model is loaded — all inference is remote, so memory usage on
the server stays minimal.
"""
import re
import math
import logging
import requests
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from backend_flask.config import HF_TOKEN, HF_EMBEDDING_MODEL
except ModuleNotFoundError:
    from config import HF_TOKEN, HF_EMBEDDING_MODEL


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str, max_chars: int = 1500, overlap: int = 200) -> List[str]:
    text = re.sub(r'\s+', ' ', text).strip()
    boilerplate = {
        'vision', 'mission', 'program outcome', 'course objective',
        'table of contents', 'index', 'preface', 'acknowledgement'
    }
    chunks, start = [], 0
    while start < len(text):
        end = start + max_chars
        if end >= len(text):
            chunks.append(text[start:])
            break
        m = re.search(r'[.!?]\s+', text[max(0, end - 100):end + 100])
        if m:
            end = max(0, end - 100) + m.end()
        chunks.append(text[start:end].strip())
        start = end - overlap

    filtered = []
    for c in chunks:
        if len(c) < 50:
            continue
        c_lower = c.lower()
        if len(c) < 500 and any(kw in c_lower for kw in boilerplate):
            continue
        if sum(1 for kw in boilerplate if kw in c_lower) >= 2:
            continue
        filtered.append(c)
    return filtered


# ---------------------------------------------------------------------------
# Embeddings via HuggingFace Inference API
# ---------------------------------------------------------------------------

def _get_embeddings(texts: List[str]) -> Optional[List[List[float]]]:
    """Return embeddings from HF Inference API, or None on failure."""
    if not HF_TOKEN:
        return None
    url = f'https://api-inference.huggingface.co/models/{HF_EMBEDDING_MODEL}'
    headers = {'Authorization': f'Bearer {HF_TOKEN}'}
    try:
        resp = requests.post(url, headers=headers, json={'inputs': texts}, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data and isinstance(data[0], list):
                return data
        logger.warning(f'HF API returned {resp.status_code}: {resp.text[:200]}')
    except Exception as e:
        logger.warning(f'HF embedding request failed: {e}')
    return None


# ---------------------------------------------------------------------------
# Pure-Python cosine similarity (no numpy)
# ---------------------------------------------------------------------------

def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))

def _norm(v: List[float]) -> float:
    return math.sqrt(sum(x * x for x in v))

def _cosine(a: List[float], b: List[float]) -> float:
    na, nb = _norm(a), _norm(b)
    return _dot(a, b) / (na * nb) if na and nb else 0.0


# ---------------------------------------------------------------------------
# Greedy max-diversity selection (Max Marginal Relevance style)
# ---------------------------------------------------------------------------

def _select_diverse(chunks: List[str], embeddings: List[List[float]], budget: int) -> List[str]:
    """Pick 'budget' chunks that maximise coverage of the embedding space."""
    n = len(chunks)
    if n <= budget:
        return chunks

    selected_idx: List[int] = []
    # Always include the first and last chunk for document-level context
    selected_idx.append(0)
    if n > 1:
        selected_idx.append(n - 1)

    remaining = [i for i in range(n) if i not in selected_idx]

    while len(selected_idx) < budget and remaining:
        best_i, best_score = None, -1.0
        for i in remaining:
            # Score = 1 - max cosine similarity to any already-selected chunk
            # High score = very different from everything selected so far
            max_sim = max(_cosine(embeddings[i], embeddings[j]) for j in selected_idx)
            diversity = 1.0 - max_sim
            if diversity > best_score:
                best_score = diversity
                best_i = i
        if best_i is None:
            break
        selected_idx.append(best_i)
        remaining.remove(best_i)

    # Return in document order
    selected_idx.sort()
    return [chunks[i] for i in selected_idx]


# ---------------------------------------------------------------------------
# Fallback: evenly-spaced sampling
# ---------------------------------------------------------------------------

def _select_evenly(chunks: List[str], max_output_chars: int) -> str:
    total = len(chunks)
    step = max(1, total // 20)
    selected, char_count = [], 0
    for i in range(0, total, step):
        c = chunks[i]
        if char_count + len(c) > max_output_chars:
            break
        selected.append(c)
        char_count += len(c)
    return '\n\n'.join(selected) if selected else ''


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def condense_text(text: str, max_output_chars: int = 15000) -> str:
    """Return a condensed version of text fitting within max_output_chars."""
    if len(text) <= max_output_chars:
        return text

    chunks = _chunk_text(text)
    if not chunks:
        return text[:max_output_chars]

    # Estimate how many chunks fit in the budget
    avg_len = sum(len(c) for c in chunks) / len(chunks)
    budget = max(2, int(max_output_chars / avg_len))

    embeddings = _get_embeddings(chunks)

    if embeddings and len(embeddings) == len(chunks):
        selected = _select_diverse(chunks, embeddings, budget)
        result = '\n\n'.join(selected)
        logger.info(
            f'HF semantic condensation: {len(text)} → {len(result)} chars '
            f'({len(chunks)} chunks, {len(selected)} selected)'
        )
    else:
        result = _select_evenly(chunks, max_output_chars)
        logger.info(
            f'Fallback condensation: {len(text)} → {len(result)} chars'
        )

    return result or text[:max_output_chars]
