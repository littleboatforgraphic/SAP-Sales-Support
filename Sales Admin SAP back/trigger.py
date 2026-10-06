from typing import Optional, List
from glossary import GlossaryManager
import re


class TriggerDetector:
    """
    Detects when a message should trigger agent processing.
    Supports explicit prefix triggers and keyword fallback triggers.
    Uses word-boundary matching to prevent false positives.
    """

    EXPLICIT_PREFIXES = ["ai", "agent", "ai agent"]

    # Default keyword list - will be expanded from glossary in production
    DEFAULT_KEYWORDS = [
        "quotation", "quote", "invoice", "sales order", "so", "purchase order", "po",
        "delivery order", "do", "new acc", "new account", "payment", "stock", "order",
        "sebut harga", "invois", "pesanan", "stok", "bayaran"
    ]

    def __init__(self, glossary_manager: GlossaryManager):
        self.glossary_manager = glossary_manager
        self.keyword_list = self._build_keyword_list()

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

        # Check keyword fallback with word boundaries
        for keyword in self.keyword_list:
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

    def get_acknowledgement_message(self, trigger_type: str, understood_context: str) -> str:
        """
        Get the appropriate acknowledgement message based on trigger type.
        """
        if trigger_type == "explicit":
            return f"Got it — {understood_context} now."
        else:  # keyword
            return f"Noticed this looks like a {understood_context} — drafting it now. Let me know if that's not what you meant."
