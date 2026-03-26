"""Coordination analysis for disinformation detection.

Analyzes coordinated disinformation campaigns through:
- Message similarity (semantic analysis using embeddings)
- Timing correlation (publication pattern analysis)
- Source network density (clustering analysis)
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone
import json

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

logger = logging.getLogger(__name__)


class CoordinationAnalyzer:
    """
    Analyzes coordination patterns in narrative clusters.

    Uses multi-dimensional analysis to detect coordinated campaigns:
    1. Message similarity - semantic similarity using embeddings
    2. Timing correlation - publication timing patterns
    3. Network density - source clustering and relationships
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize coordination analyzer.

        Args:
            model_name: Sentence transformer model for embeddings
        """
        self.model = SentenceTransformer(model_name)
        logger.info(f"CoordinationAnalyzer initialized with model: {model_name}")

    def analyze_coordination(
        self,
        articles: List[Dict],
        time_window_hours: int = 24,
    ) -> float:
        """
        Calculate coordination score for a cluster of articles.

        Args:
            articles: List of article dicts with keys: title, description, source, pub_date, url
            time_window_hours: Time window to consider for timing analysis

        Returns:
            Coordination score (0.0-1.0)
            - 0.0: No coordination detected
            - 1.0: Maximum coordination (likely coordinated campaign)
        """
        if len(articles) < 2:
            logger.debug("Less than 2 articles, coordination score = 0")
            return 0.0

        # Component 1: Message Similarity (0-1)
        message_similarity = self._calculate_message_similarity(articles)
        logger.debug(f"Message similarity: {message_similarity:.3f}")

        # Component 2: Timing Correlation (0-1)
        timing_correlation = self._calculate_timing_correlation(articles)
        logger.debug(f"Timing correlation: {timing_correlation:.3f}")

        # Component 3: Source Network Density (0-1)
        network_density = self._calculate_network_density(articles)
        logger.debug(f"Network density: {network_density:.3f}")

        # Weighted combination
        coordination_score = (
            0.4 * message_similarity +
            0.3 * timing_correlation +
            0.3 * network_density
        )

        logger.info(
            f"Coordination analysis: {len(articles)} articles, "
            f"score={coordination_score:.3f} "
            f"(msg={message_similarity:.2f}, time={timing_correlation:.2f}, net={network_density:.2f})"
        )

        return round(coordination_score, 3)

    def _calculate_message_similarity(self, articles: List[Dict]) -> float:
        """
        Calculate semantic similarity between article texts.

        Uses sentence transformers to encode article titles + descriptions,
        then computes average pairwise cosine similarity.
        """
        # Extract text content
        texts = []
        for article in articles:
            title = article.get("title", "")
            desc = article.get("description", "")
            text = f"{title} {desc}".strip()
            if text:
                texts.append(text)

        if len(texts) < 2:
            return 0.0

        # Generate embeddings
        try:
            embeddings = self.model.encode(texts, show_progress_bar=False)
        except Exception as e:
            logger.error(f"Failed to encode texts: {e}")
            return 0.0

        # Calculate pairwise cosine similarity
        similarity_matrix = cosine_similarity(embeddings)

        # Get average similarity (excluding diagonal)
        n = len(similarity_matrix)
        total_similarity = similarity_matrix.sum() - n  # Subtract diagonal (all 1.0)
        num_pairs = n * (n - 1)

        if num_pairs == 0:
            return 0.0

        avg_similarity = total_similarity / num_pairs

        # Clamp to [0, 1] range
        return float(np.clip(avg_similarity, 0.0, 1.0))

    def _calculate_timing_correlation(self, articles: List[Dict]) -> float:
        """
        Analyze publication timing patterns.

        High correlation indicates synchronized publication (coordinated campaign).
        Low variance in inter-arrival times = high correlation.
        """
        # Extract publication timestamps
        timestamps = []
        for article in articles:
            pub_date = article.get("pub_date")
            if pub_date:
                if isinstance(pub_date, str):
                    try:
                        pub_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    except:
                        continue
                if isinstance(pub_date, datetime):
                    timestamps.append(pub_date.timestamp())

        if len(timestamps) < 2:
            return 0.0

        # Sort timestamps
        timestamps.sort()

        # Calculate inter-arrival times (seconds between consecutive articles)
        intervals = [
            timestamps[i + 1] - timestamps[i]
            for i in range(len(timestamps) - 1)
        ]

        if not intervals:
            return 0.0

        # Calculate statistics
        mean_interval = np.mean(intervals)
        std_interval = np.std(intervals)

        # Low standard deviation = high coordination
        # Normalize: if all published within 1 hour of each other, score = 1.0
        if mean_interval == 0:
            return 1.0

        # Coefficient of variation
        cv = std_interval / mean_interval if mean_interval > 0 else 0

        # Convert to correlation score (0-1)
        # CV = 0 (all published at same time) → score = 1.0
        # CV = 2 (high variance) → score ≈ 0.0
        correlation = np.exp(-cv)

        return float(np.clip(correlation, 0.0, 1.0))

    def _calculate_network_density(self, articles: List[Dict]) -> float:
        """
        Calculate source network density.

        Measures how interconnected the sources are:
        - All from same source: high density
        - Many unique sources: lower density (unless they share patterns)
        - Repeated source pairs: higher density
        """
        sources = [article.get("source", "unknown") for article in articles]
        unique_sources = set(sources)

        if len(unique_sources) == 1:
            # All from same source - highly suspicious
            return 0.85

        if len(unique_sources) == len(sources):
            # All unique sources - low coordination
            return 0.1

        # Calculate source repetition ratio
        repetition_ratio = 1.0 - (len(unique_sources) / len(sources))

        # Build co-occurrence matrix for source pairs
        source_pairs = {}
        for i in range(len(sources)):
            for j in range(i + 1, len(sources)):
                pair = tuple(sorted([sources[i], sources[j]]))
                source_pairs[pair] = source_pairs.get(pair, 0) + 1

        # Calculate network density
        # More repeated pairs = higher density
        max_possible_pairs = len(sources) * (len(sources) - 1) // 2
        actual_unique_pairs = len(source_pairs)

        if max_possible_pairs == 0:
            return 0.0

        # Density score based on both repetition and pair overlap
        density = 0.5 * repetition_ratio + 0.5 * (1.0 - actual_unique_pairs / max_possible_pairs)

        return float(np.clip(density, 0.0, 1.0))

    def analyze_with_details(
        self,
        articles: List[Dict],
        time_window_hours: int = 24,
    ) -> Dict:
        """
        Analyze coordination with detailed breakdown.

        Returns:
            Dict with keys: coordination_score, message_similarity, timing_correlation,
                           network_density, article_count, unique_sources
        """
        if len(articles) < 2:
            return {
                "coordination_score": 0.0,
                "message_similarity": 0.0,
                "timing_correlation": 0.0,
                "network_density": 0.0,
                "article_count": len(articles),
                "unique_sources": len(set(a.get("source") for a in articles)),
            }

        message_similarity = self._calculate_message_similarity(articles)
        timing_correlation = self._calculate_timing_correlation(articles)
        network_density = self._calculate_network_density(articles)

        coordination_score = (
            0.4 * message_similarity +
            0.3 * timing_correlation +
            0.3 * network_density
        )

        sources = [a.get("source", "unknown") for a in articles]

        return {
            "coordination_score": round(coordination_score, 3),
            "message_similarity": round(message_similarity, 3),
            "timing_correlation": round(timing_correlation, 3),
            "network_density": round(network_density, 3),
            "article_count": len(articles),
            "unique_sources": len(set(sources)),
            "source_list": list(set(sources))[:10],  # Top 10 unique sources
        }
