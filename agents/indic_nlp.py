"""Indic NLP Agent — Indian Language Understanding Layer.

Supports 12 major Indian languages for:
  1. Script detection (Devanagari, Bengali, Tamil, Telugu, Kannada, etc.)
  2. Sentiment analysis using IndicBERT (ai4bharat/indic-bert)
  3. Named entity recognition in regional-language content
  4. Transliteration normalization for better entity matching
  5. Language routing — decides if an article needs Indic or English processing

Design: Lazy-loads models on first use to avoid startup penalty.
Falls back gracefully if transformers/IndicBERT is not installed.

Models (install with):
    pip install transformers sentencepiece
    # For IndicBERT: download automatically via Hugging Face hub
    # Model ID: ai4bharat/indic-bert (~500MB)

Usage:
    agent = IndicNLPAgent()
    result = agent.analyze("मोदी सरकार ने नया रक्षा बजट घोषित किया")
    # result.language == "hi"
    # result.sentiment == "neutral"
    # result.entities == [{"text": "मोदी", "type": "Person"}, ...]
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# ── Script detection ranges ───────────────────────────────────────────────────
_SCRIPT_RANGES = {
    "hi": (0x0900, 0x097F),   # Devanagari — Hindi, Marathi, Sanskrit
    "mr": (0x0900, 0x097F),   # Devanagari — Marathi (same script)
    "bn": (0x0980, 0x09FF),   # Bengali
    "pa": (0x0A00, 0x0A7F),   # Gurmukhi — Punjabi
    "gu": (0x0A80, 0x0AFF),   # Gujarati
    "or": (0x0B00, 0x0B7F),   # Odia
    "ta": (0x0B80, 0x0BFF),   # Tamil
    "te": (0x0C00, 0x0C7F),   # Telugu
    "kn": (0x0C80, 0x0CFF),   # Kannada
    "ml": (0x0D00, 0x0D7F),   # Malayalam
    "ur": (0x0600, 0x06FF),   # Arabic/Perso-Arabic — Urdu
}

# Language code → display name
_LANG_NAMES = {
    "hi": "Hindi", "mr": "Marathi", "bn": "Bengali", "pa": "Punjabi",
    "gu": "Gujarati", "or": "Odia", "ta": "Tamil", "te": "Telugu",
    "kn": "Kannada", "ml": "Malayalam", "ur": "Urdu", "en": "English",
}

# Minimum Indic character fraction to consider text "Indic"
_INDIC_THRESHOLD = 0.15


@dataclass
class IndicAnalysisResult:
    text: str
    language: str                    # ISO 639-1 code: "hi", "ta", "en", etc.
    language_name: str
    is_indic: bool
    script: Optional[str] = None     # Script name if Indic

    # Sentiment: positive / negative / neutral
    sentiment: str = "neutral"
    sentiment_score: float = 0.0     # Positive class probability
    sentiment_model: str = "rule"    # "indicbert" | "rule"

    # Entities extracted from Indic text
    entities: list[dict] = field(default_factory=list)

    # Transliterated version (Devanagari → Latin for entity matching)
    transliterated: Optional[str] = None


class IndicNLPAgent:
    """Multilingual NLP agent for Indian-language content.

    Provides:
    - Fast script detection (regex, no model needed)
    - IndicBERT sentiment analysis (lazy-loaded from Hugging Face)
    - Regex-based NER heuristics for Indic text when transformers unavailable
    - Transliteration normalization via indic-transliteration library
    """

    def __init__(self, use_gpu: bool = False):
        self._sentiment_pipe = None
        self._ner_pipe = None
        self._transliterator = None
        self._use_gpu = use_gpu
        self._models_attempted = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def analyze(self, text: str) -> IndicAnalysisResult:
        """Full analysis: language detection → sentiment → NER.

        Automatically decides whether to use IndicBERT (Indic text)
        or skip (English text, handled by the main extraction pipeline).
        """
        if not text or not text.strip():
            return IndicAnalysisResult(
                text=text, language="en", language_name="English",
                is_indic=False
            )

        lang, script = self.detect_language(text)
        is_indic = lang != "en"

        result = IndicAnalysisResult(
            text=text,
            language=lang,
            language_name=_LANG_NAMES.get(lang, lang),
            is_indic=is_indic,
            script=script,
        )

        if is_indic:
            # Sentiment analysis
            sentiment, score, model = self.analyze_sentiment(text, lang)
            result.sentiment = sentiment
            result.sentiment_score = score
            result.sentiment_model = model

            # Entity extraction
            result.entities = self.extract_entities_indic(text, lang)

            # Transliteration (for Devanagari → entity matching)
            if lang in ("hi", "mr"):
                result.transliterated = self.transliterate_devanagari(text)

        return result

    def analyze_batch(self, texts: list[str]) -> list[IndicAnalysisResult]:
        """Analyze multiple texts, routing Indic texts through IndicBERT in batch."""
        results = []
        indic_indices = []
        indic_texts = []

        # First pass: language detection
        for i, text in enumerate(texts):
            lang, script = self.detect_language(text)
            is_indic = lang != "en"
            result = IndicAnalysisResult(
                text=text,
                language=lang,
                language_name=_LANG_NAMES.get(lang, lang),
                is_indic=is_indic,
                script=script,
            )
            results.append(result)
            if is_indic:
                indic_indices.append(i)
                indic_texts.append(text)

        # Batch sentiment for Indic texts
        if indic_texts:
            sentiments = self._batch_sentiment(indic_texts)
            for idx, (i, text) in enumerate(zip(indic_indices, indic_texts)):
                sentiment, score, model = sentiments[idx]
                results[i].sentiment = sentiment
                results[i].sentiment_score = score
                results[i].sentiment_model = model
                results[i].entities = self.extract_entities_indic(text, results[i].language)

        return results

    # ── Language / Script Detection ────────────────────────────────────────────

    def detect_language(self, text: str) -> tuple[str, Optional[str]]:
        """Detect language from Unicode script ranges.

        Returns (lang_code, script_name). Falls back to "en" if primarily Latin.
        """
        if not text:
            return "en", None

        char_counts: dict[str, int] = {}
        total_alpha = 0

        for char in text:
            cp = ord(char)
            if unicodedata.category(char).startswith("L"):
                total_alpha += 1
                for lang, (lo, hi) in _SCRIPT_RANGES.items():
                    if lo <= cp <= hi:
                        char_counts[lang] = char_counts.get(lang, 0) + 1
                        break

        if total_alpha == 0:
            return "en", None

        # Find dominant script
        if not char_counts:
            return "en", None

        dominant_lang = max(char_counts, key=lambda k: char_counts[k])
        dominant_frac = char_counts[dominant_lang] / total_alpha

        if dominant_frac < _INDIC_THRESHOLD:
            return "en", None

        script_names = {
            "hi": "Devanagari", "mr": "Devanagari",
            "bn": "Bengali", "pa": "Gurmukhi", "gu": "Gujarati",
            "or": "Odia", "ta": "Tamil", "te": "Telugu",
            "kn": "Kannada", "ml": "Malayalam", "ur": "Perso-Arabic",
        }
        return dominant_lang, script_names.get(dominant_lang)

    # ── Sentiment Analysis ─────────────────────────────────────────────────────

    def analyze_sentiment(
        self, text: str, lang: str = "hi"
    ) -> tuple[str, float, str]:
        """Analyze sentiment of Indic text.

        Returns: (sentiment_label, positive_probability, model_name)
        """
        pipe = self._get_sentiment_pipeline()
        if pipe:
            try:
                # Truncate to 512 tokens
                result = pipe(text[:512], truncation=True, max_length=512)
                label = result[0]["label"].lower()
                score = result[0]["score"]
                # Map IndicBERT labels to standard form
                if "pos" in label:
                    return "positive", score, "indicbert"
                elif "neg" in label:
                    return "negative", score, "indicbert"
                else:
                    return "neutral", score, "indicbert"
            except Exception as e:
                logger.debug(f"IndicBERT sentiment failed: {e}")

        # Fallback: rule-based sentiment via keyword lists
        return self._rule_based_sentiment(text)

    def _batch_sentiment(
        self, texts: list[str]
    ) -> list[tuple[str, float, str]]:
        """Batch sentiment, reusing pipeline for efficiency."""
        pipe = self._get_sentiment_pipeline()
        if pipe:
            try:
                truncated = [t[:512] for t in texts]
                results = pipe(truncated, truncation=True, max_length=512, batch_size=8)
                sentiments = []
                for r in results:
                    label = r["label"].lower()
                    score = r["score"]
                    if "pos" in label:
                        sentiments.append(("positive", score, "indicbert"))
                    elif "neg" in label:
                        sentiments.append(("negative", score, "indicbert"))
                    else:
                        sentiments.append(("neutral", score, "indicbert"))
                return sentiments
            except Exception as e:
                logger.debug(f"IndicBERT batch sentiment failed: {e}")

        return [self._rule_based_sentiment(t) for t in texts]

    def _rule_based_sentiment(self, text: str) -> tuple[str, float, str]:
        """Simple keyword-based sentiment for Devanagari + English fallback."""
        # Hindi positive signals
        positive_words = [
            "सफल", "विकास", "समझौता", "सहयोग", "शांति", "प्रगति",
            "वृद्धि", "निवेश", "positive", "growth", "peace", "agreement",
        ]
        negative_words = [
            "युद्ध", "संघर्ष", "हमला", "खतरा", "प्रतिबंध", "हिंसा",
            "संकट", "विफल", "war", "attack", "crisis", "sanction", "threat",
        ]
        text_lower = text.lower()
        pos_hits = sum(1 for w in positive_words if w in text_lower)
        neg_hits = sum(1 for w in negative_words if w in text_lower)

        if pos_hits > neg_hits:
            return "positive", 0.6 + min(pos_hits * 0.05, 0.35), "rule"
        elif neg_hits > pos_hits:
            return "negative", 0.6 + min(neg_hits * 0.05, 0.35), "rule"
        return "neutral", 0.5, "rule"

    # ── Named Entity Recognition ───────────────────────────────────────────────

    def extract_entities_indic(self, text: str, lang: str) -> list[dict]:
        """Extract named entities from Indic text.

        Uses a heuristic approach: capitalized sequences in mixed Indic/Latin
        text (code-mixed news is very common in Indian journalism).
        For pure Indic text, relies on IndicBERT NER if available.
        """
        entities = []

        # Extract Latin-script named entities from code-mixed text (very common in Indian news)
        latin_entities = re.findall(
            r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b', text
        )
        for e in latin_entities:
            if len(e) > 2 and e not in {
                "The", "In", "At", "On", "By", "To", "For", "But", "And",
                "Of", "Up", "As", "Or", "An"
            }:
                entities.append({"text": e, "type": "Unknown", "source": "code_mixed"})

        # Try IndicBERT NER (if available)
        ner_pipe = self._get_ner_pipeline()
        if ner_pipe:
            try:
                ner_results = ner_pipe(text[:512], aggregation_strategy="simple")
                for r in ner_results:
                    if r["score"] > 0.7:
                        type_map = {
                            "PER": "Person", "ORG": "Organization",
                            "LOC": "Location", "GPE": "Country",
                            "MISC": "Organization",
                        }
                        entities.append({
                            "text": r["word"],
                            "type": type_map.get(r["entity_group"], r["entity_group"]),
                            "confidence": r["score"],
                            "source": "indicbert_ner",
                        })
            except Exception as e:
                logger.debug(f"IndicBERT NER failed: {e}")

        # Deduplicate by text
        seen = set()
        unique = []
        for e in entities:
            if e["text"] not in seen:
                seen.add(e["text"])
                unique.append(e)

        return unique[:15]

    # ── Transliteration ───────────────────────────────────────────────────────

    def transliterate_devanagari(self, text: str) -> Optional[str]:
        """Transliterate Devanagari → IAST Latin using indic-transliteration."""
        try:
            from indic_transliteration import sanscript
            from indic_transliteration.sanscript import transliterate
            return transliterate(text, sanscript.DEVANAGARI, sanscript.IAST)
        except ImportError:
            # Graceful degradation — transliteration is enhancement, not core
            return None
        except Exception as e:
            logger.debug(f"Transliteration failed: {e}")
            return None

    # ── Lazy Model Loading ─────────────────────────────────────────────────────

    def _get_sentiment_pipeline(self):
        """Lazy-load IndicBERT sentiment pipeline."""
        if self._sentiment_pipe is not None:
            return self._sentiment_pipe
        if self._models_attempted:
            return None

        self._models_attempted = True
        try:
            from transformers import pipeline
            device = 0 if self._use_gpu else -1
            logger.info("Loading multilingual sentiment model (nlptown/bert-base-multilingual-uncased-sentiment)...")
            self._sentiment_pipe = pipeline(
                "text-classification",
                model="nlptown/bert-base-multilingual-uncased-sentiment",
                device=device,
                truncation=True,
            )
            logger.info("Sentiment model loaded successfully")
        except ImportError:
            logger.warning(
                "transformers not installed. Using rule-based sentiment. "
                "Install with: pip install transformers sentencepiece"
            )
        except Exception as e:
            logger.warning(f"IndicBERT model load failed (rule-based fallback): {e}")

        return self._sentiment_pipe

    def _get_ner_pipeline(self):
        """Lazy-load IndicBERT NER pipeline."""
        if self._ner_pipe is not None:
            return self._ner_pipe
        # Only attempt NER if base model loaded successfully
        if self._models_attempted and self._sentiment_pipe is None:
            return None
        try:
            from transformers import pipeline
            device = 0 if self._use_gpu else -1
            self._ner_pipe = pipeline(
                "ner",
                model="Davlan/bert-base-multilingual-cased-ner-hrl",
                device=device,
                aggregation_strategy="simple",
            )
            logger.info("Multilingual NER model loaded")
        except Exception as e:
            logger.debug(f"IndicNER load skipped: {e}")
        return self._ner_pipe

    # ── Utility ───────────────────────────────────────────────────────────────

    def is_indic_text(self, text: str) -> bool:
        lang, _ = self.detect_language(text)
        return lang != "en"

    def get_language_name(self, text: str) -> str:
        lang, _ = self.detect_language(text)
        return _LANG_NAMES.get(lang, "Unknown")

    def sentiment_batch_for_entity(
        self, entity_name: str, texts: list[str]
    ) -> dict:
        """Compute average sentiment for an entity across a set of texts.

        Returns: {entity, avg_sentiment_score, dominant_sentiment, sample_count}
        Used by DisinfoDetector to detect sentiment manipulation.
        """
        results = self.analyze_batch(texts)
        scores = [r.sentiment_score for r in results if r.is_indic]
        if not scores:
            return {
                "entity": entity_name,
                "sample_count": 0,
                "avg_sentiment_score": None,
                "dominant_sentiment": "unknown",
            }

        avg = sum(scores) / len(scores)
        labels = [r.sentiment for r in results if r.is_indic]
        dominant = max(set(labels), key=labels.count)
        return {
            "entity": entity_name,
            "sample_count": len(scores),
            "avg_sentiment_score": round(avg, 3),
            "dominant_sentiment": dominant,
        }
