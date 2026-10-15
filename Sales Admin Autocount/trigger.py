from typing import Optional, List
from glossary import GlossaryManager
from sqlalchemy.orm import Session
import re


class TriggerDetector:
    """
    Detects when a message should trigger agent processing.
    Supports explicit prefix triggers and keyword fallback triggers.
    Uses word-boundary matching to prevent false positives.
    Learns new trigger keywords dynamically from user interactions.
    """

    EXPLICIT_PREFIXES = ["ai", "agent", "ai agent"]

    # Default keyword list - will be expanded from glossary in production
    DEFAULT_KEYWORDS = [
        "quotation", "quote", "invoice", "sales order", "so", "purchase order", "po",
        "delivery order", "do", "new acc", "new account", "payment", "stock", "order",
        "sebut harga", "invois", "pesanan", "stok", "bayaran", "AI", "ai agent", "agent"
    ]

    def __init__(self, glossary_manager: GlossaryManager, db: Session = None):
        self.glossary_manager = glossary_manager
        self.db = db
        self.keyword_list = self._build_keyword_list()
        self._learned_keywords_cache = None
        self._cache_expiry = None

    def _build_keyword_list(self) -> List[str]:
        """
        Build keyword list from glossary entries with category BUSINESS_TERM.
        Falls back to default keywords if glossary is empty.
        """
        approved_entries = self.glossary_manager.get_approved_entries()
        business_terms = [
            entry.term for entry in approved_entries
            if entry.category.value == "business_term"
        ]

        if business_terms:
            return business_terms
        return self.DEFAULT_KEYWORDS

    def _get_learned_trigger_keywords(self) -> List[str]:
        """Get dynamically learned trigger keywords from database."""
        if not self.db:
            return []
        
        # Simple cache
        if self._learned_keywords_cache and self._cache_expiry:
            from datetime import datetime, timezone, timedelta
            if datetime.now(timezone.utc) < self._cache_expiry:
                return self._learned_keywords_cache

        try:
            from database import LearnedTriggerKeyword
            learned = self.db.query(LearnedTriggerKeyword).filter(
                LearnedTriggerKeyword.agent_type == "trigger",  # Special agent type for general triggers
                LearnedTriggerKeyword.active == True,
                LearnedTriggerKeyword.confidence >= 0.7
            ).all()

            keywords = [entry.keyword for entry in learned]
            self._learned_keywords_cache = keywords
            from datetime import datetime, timezone, timedelta
            self._cache_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
            return keywords
        except Exception as e:
            # If table doesn't exist yet, return empty
            return []

    def detect(self, message: str) -> Optional[str]:
        """
        Detect if message should trigger agent processing.
        Returns "explicit" if explicit prefix is used.
        Returns "keyword" if keyword fallback matches.
        Returns None if no trigger detected.
        """
        normalized = message.strip().lower()

        # Check explicit prefixes with word boundary
        for prefix in self.EXPLICIT_PREFIXES:
            # Use regex to match word boundary at start
            pattern = rf"^{re.escape(prefix)}\b"
            if re.search(pattern, normalized):
                return "explicit"

        # Build full keyword list (default + learned)
        all_keywords = self.keyword_list.copy()
        learned_keywords = self._get_learned_trigger_keywords()
        all_keywords.extend(learned_keywords)

        # Check keyword fallback with word boundaries
        for keyword in all_keywords:
            # Use word boundaries to prevent partial matches
            pattern = rf"\b{re.escape(keyword)}\b"
            if re.search(pattern, normalized):
                # Additional guard: for single-word keywords that are common in casual chat,
                # require at least one business-intent context word
                if self._is_risky_keyword(keyword):
                    if not self._has_business_context(normalized):
                        continue
                return "keyword"

        return None

    def _is_risky_keyword(self, keyword: str) -> bool:
        """
        Determine if a keyword is too common in casual conversation.
        Single short words like "order" are risky.
        """
        risky_keywords = ["order", "so", "do"]
        return keyword.lower() in risky_keywords

    def _has_business_context(self, message: str) -> bool:
        """
        Check if message contains business-intent context words.
        This prevents triggering on casual mentions of risky keywords.
        """
        business_contexts = [
            "new", "create", "check", "get", "send", "draft", "confirm",
            "price", "stock", "quote", "invoice", "delivery", "po", "purchase"
        ]

        for context in business_contexts:
            pattern = rf"\b{re.escape(context)}\b"
            if re.search(pattern, message):
                return True

        return False

    def learn_new_trigger_keyword(self, message: str, confidence: float = 0.8):
        """
        Learn a new trigger keyword from a successfully triggered message.
        """
        if not self.db:
            return

        from database import LearnedTriggerKeyword
        from dynamic_router import DynamicRouter

        # Extract potential keywords
        words = re.findall(r'\b\w+\b', message.lower())
        
        # Filter out common words
        filtered_words = [
            word for word in words
            if word not in DynamicRouter.COMMON_WORDS and len(word) >= 3
        ]
        
        # Add words as potential trigger keywords
        for word in filtered_words:
            # Check if already exists
            existing = self.db.query(LearnedTriggerKeyword).filter(
                LearnedTriggerKeyword.keyword == word,
                LearnedTriggerKeyword.agent_type == "trigger"
            ).first()
            
            if existing:
                existing.usage_count += 1
                existing.success_count += 1
                existing.confidence = min(existing.confidence + 0.05, 1.0)
                from datetime import datetime, timezone
                existing.last_used_at = datetime.now(timezone.utc)
            else:
                new_keyword = LearnedTriggerKeyword(
                    keyword=word,
                    agent_type="trigger",  # Special type for general triggers
                    confidence=confidence,
                    usage_count=1,
                    success_count=1
                )
                self.db.add(new_keyword)
        
        self.db.commit()
        
        # Clear cache
        self._learned_keywords_cache = None
        self._cache_expiry = None

    def get_acknowledgement_message(self, trigger_type: str, understood_context: str) -> str:
        """
        Get the appropriate acknowledgement message based on trigger type.
        """
        if trigger_type == "explicit":
            return f"Got it — {understood_context} now."
        else:  # keyword
            return f"Noticed this looks like a {understood_context} — drafting it now. Let me know if that's not what you meant."
