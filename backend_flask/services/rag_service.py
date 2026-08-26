"""RAG condensation service (inlined from the former standalone ML service)."""
import logging
import re
from typing import List

logger = logging.getLogger(__name__)


class RAGProcessor:
    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("SentenceTransformer loaded.")
        except Exception as e:
            logger.error(f"Failed to load SentenceTransformer: {e}")
            self.model = None

    def chunk_text(self, text: str, max_chars: int = 1500, overlap: int = 200) -> List[str]:
        """Split text into overlapping chunks, filtering boilerplate."""
        text = re.sub(r'\s+', ' ', text).strip()
        chunks = []
        start = 0
        while start < len(text):
            end = start + max_chars
            if end >= len(text):
                chunks.append(text[start:])
                break
            match = re.search(r'[.!?]\s+', text[end - 100:end + 100])
            if match:
                end = (end - 100) + match.end()
            chunks.append(text[start:end].strip())
            start = end - overlap

        boilerplate = [
            'vision', 'mission', 'program outcome', 'course objective',
            'table of contents', 'index', 'preface', 'acknowledgement'
        ]
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

    def condense_text(self, text: str, max_output_chars: int = 15000) -> str:
        """Return the most representative chunks via KMeans clustering."""
        if not self.model:
            return text[:max_output_chars]
        if len(text) <= max_output_chars:
            return text

        chunks = self.chunk_text(text)
        if not chunks:
            return ""

        try:
            from sklearn.cluster import KMeans
            from sklearn.metrics import pairwise_distances_argmin_min

            embeddings = self.model.encode(chunks)
            avg_chunk_size = sum(len(c) for c in chunks) / len(chunks)
            num_clusters = max(2, min(len(chunks), int(max_output_chars / avg_chunk_size)))

            if num_clusters >= len(chunks):
                return "\n\n".join(chunks)

            kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init="auto")
            kmeans.fit(embeddings)
            closest_indices, _ = pairwise_distances_argmin_min(kmeans.cluster_centers_, embeddings)
            selected = [chunks[i] for i in sorted(closest_indices)]
            logger.info(f"RAG: {len(chunks)} chunks → {len(selected)} representative chunks.")
            return "\n\n".join(selected)
        except Exception as e:
            logger.error(f"RAG clustering failed: {e}")
            return text[:max_output_chars]


_rag_processor: RAGProcessor | None = None


def get_rag_processor() -> RAGProcessor:
    global _rag_processor
    if _rag_processor is None:
        _rag_processor = RAGProcessor()
    return _rag_processor
