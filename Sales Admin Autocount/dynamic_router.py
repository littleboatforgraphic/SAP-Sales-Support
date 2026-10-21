"""
Dynamic learning system for agent routing and trigger detection.

This module learns from user interactions to:
1. Improve routing accuracy between agents
2. Detect new trigger keywords automatically
3. Adapt to user behavior patterns

Routing:
    - Keywords are matched on word boundaries (not substrings). Longer phrases
      claim their text first, so "new customer" is not also counted as "customer".
    - Weak/generic keywords and learned keywords count for half a point.
    - Ties and weak evidence fall through to the LLM (in "hybrid" mode).

Learning (conservative, stays on):
    - A learned keyword starts below the activation threshold and only goes live
      after repeated confirmed uses (MIN_LEARNED_USES).
    - Learned keywords never outvote base keywords (weight 0.5).
    - Confidence drops when a keyword was present on a misrouted message, and the
      keyword is deactivated if that keeps happening.
"""

import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Tunables
# --------------------------------------------------------------------------

ACTIVE_THRESHOLD = 0.7          # learned keyword must reach this confidence to be used
MIN_LEARNED_USES = 3            # ...and have been confirmed this many times
INITIAL_CONFIDENCE = 0.5        # new learned keywords start here (below ACTIVE_THRESHOLD)
CONFIDENCE_STEP = 0.1           # added on each confirmed use
PENALTY_STEP = 0.25             # removed when the keyword was on a misrouted message
DEACTIVATE_AT = 0.2             # at/below this confidence the keyword is switched off
MAX_NEW_KEYWORDS_PER_MESSAGE = 5
MAX_CANDIDATE_WORDS = 15
LEARNED_WEIGHT = 0.5            # learned keywords count for half a point
WEAK_WEIGHT = 0.5               # so do generic base keywords (see WEAK_KEYWORDS)
MIN_KEYWORD_SCORE = 1.0         # hybrid mode: below this, ask the LLM instead
CACHE_TTL_MINUTES = 5
MAX_LOGGED_MESSAGE_CHARS = 500

# Feedback vocabulary understood by record_user_feedback (edit to match your UI).
POSITIVE_FEEDBACK = frozenset({"correct", "right", "good", "positive", "thumbs_up", "up", "yes", "helpful"})
NEGATIVE_FEEDBACK = frozenset({"incorrect", "wrong", "bad", "negative", "thumbs_down", "down", "no"})

# Keywords that are prefixes (e.g. debtor codes "300-A0001"): no right-hand word boundary.
# Anything ending in "-" (e.g. "wm-") is treated as a prefix automatically.
PREFIX_KEYWORDS = frozenset({"300-a"})

# Words that look like intent but are really generic/ambiguous, or who is writing
# rather than what they want (customer names, debtor codes). They count for half.
_WEAK_KEYWORDS = frozenset({
    "customer", "client", "debtor", "available", "bank", "transaction",
    "300-a", "abc trading", "xyz construction", "buildwell",
})

# Words in COMMON_WORDS that are actually useful domain vocabulary, so they may be learned.
_DOMAIN_WORDS = frozenset({
    "pay", "pays", "paying", "paid",
    "sell", "sells", "sold", "selling", "buy", "buys", "bought", "buying",
})

# Greetings, sign-offs, filler and Malay function words that must never be learned.
_EXTRA_STOPWORDS = frozenset({
    "please", "pls", "plz", "thanks", "thank", "thx", "hello", "hey", "dear", "regards",
    "best", "sincerely", "kindly", "sir", "madam", "morning", "afternoon", "evening",
    "attached", "attach", "attachment", "email", "mail", "below", "following", "hope",
    "well", "good", "great", "info", "information", "detail", "details", "regarding",
    "request", "requested", "enquiry", "inquiry", "urgent", "asap", "today", "tomorrow",
    "week", "day", "time", "ref", "know", "sdn", "bhd", "ltd", "pte",
    "yang", "untuk", "saya", "dan", "dengan", "ini", "itu", "boleh", "tolong", "terima",
    "kasih", "ada", "mahu", "nak", "sila", "tuan", "puan", "dari", "kepada", "pada",
})


@lru_cache(maxsize=4096)
def _compile_keyword(kw: str) -> "re.Pattern":
    """Word-boundary pattern for a keyword. CJK keywords use plain substring matching."""
    escaped = re.escape(kw)
    if any(ord(ch) >= 0x2E80 for ch in kw):
        return re.compile(escaped)
    right = "" if (kw.endswith("-") or kw in PREFIX_KEYWORDS) else r"(?!\w)"
    return re.compile(r"(?<!\w)" + escaped + right)


def _safe_message(message: str) -> str:
    """Truncate and mask emails before a message is stored in the routing log."""
    text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "[email]", message or "")
    return text[:MAX_LOGGED_MESSAGE_CHARS]


class DynamicRouter:
    """Dynamic routing system that learns from user interactions."""

    # Base keywords for each agent (hardcoded defaults)
    BASE_KEYWORDS = {
        "order_invoice": [
            "customer", "client", "debtor", "300-a", "abc trading", "xyz construction", "buildwell",
            "order", "orders", "invoice", "invoices", "po", "purchase order", "purchase orders",
            "sales order", "sales orders",
            "pesanan", "invois", "订单", "发票",
        ],
        "stock_quote": [
            "stock", "stocks", "in stock", "quote", "quotes", "quotation", "quotations",
            "price", "prices", "pricing", "inventory", "available", "wm-", "brc-", "weld",
            "harga", "stok", "报价", "价格", "库存",
        ],
        "shipment": [
            "shipment", "shipments", "shipping", "shipped", "ship", "delivery", "deliveries",
            "deliver", "delivered", "pickup", "pick up", "pack", "packing", "packed",
            "hantar", "penghantaran", "送货", "发货",
        ],
        "customer_onboarding": [
            "new customer", "customer onboarding", "register", "registration", "onboard",
            "new account",
        ],
        "payment_followup": [
            "payment", "payments", "paid", "receipt", "transaction", "bank", "remittance",
            "bayaran", "bayar", "付款", "收据",
        ],
    }

    WEAK_KEYWORDS = _WEAK_KEYWORDS

    # Common words to filter out when learning new keywords
    COMMON_WORDS = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "have", "has", "had",
        "do", "does", "did", "will", "would", "could", "should", "may", "might", "can",
        "need", "want", "like", "just", "also", "very", "too", "so", "if", "then", "than",
        "because", "as", "until", "while", "of", "at", "by", "for", "with", "about",
        "against", "between", "into", "through", "during", "before", "after", "above",
        "below", "to", "from", "up", "down", "in", "out", "on", "off", "over", "under",
        "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
        "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
        "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "s", "t",
        "can", "will", "just", "don", "should", "now", "i", "you", "me", "my", "your",
        "we", "our", "this", "that", "these", "those", "am", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "did", "done", "does", "doing",
        "get", "gets", "got", "getting", "give", "gives", "gave", "giving", "make", "makes",
        "made", "making", "know", "knows", "knew", "knowing", "think", "thinks", "thought",
        "thinking", "take", "takes", "took", "taking", "see", "sees", "saw", "seeing",
        "come", "came", "coming", "want", "wants", "wanted", "wants", "use", "uses",
        "used", "using", "call", "calls", "called", "calling", "try", "tries", "tried",
        "trying", "ask", "asks", "asked", "asking", "work", "works", "worked", "working",
        "need", "needs", "needed", "needing", "feel", "feels", "felt", "feeling", "leave",
        "leaves", "left", "leaving", "put", "puts", "putting", "mean", "means", "meant",
        "meaning", "keep", "keeps", "kept", "keeping", "let", "lets", "letting", "begin",
        "begins", "began", "beginning", "seem", "seems", "seemed", "seeming", "help",
        "helps", "helped", "helping", "show", "shows", "showed", "showing", "hear", "hears",
        "heard", "hearing", "play", "plays", "played", "playing", "run", "runs", "ran",
        "running", "move", "moves", "moved", "moving", "live", "lives", "lived", "living",
        "believe", "believes", "believed", "believing", "hold", "holds", "held", "holding",
        "bring", "brings", "brought", "bringing", "happen", "happens", "happened", "happening",
        "write", "writes", "wrote", "writing", "provide", "provides", "provided", "providing",
        "sit", "sits", "sat", "sitting", "stand", "stands", "stood", "standing", "lose",
        "loses", "lost", "losing", "pay", "pays", "paid", "paying", "meet", "meets", "met",
        "meeting", "include", "includes", "included", "including", "continue", "continues",
        "continued", "continuing", "set", "sets", "set", "setting", "learn", "learns",
        "learned", "learning", "change", "changes", "changed", "changing", "lead", "leads",
        "led", "leading", "understand", "understands", "understood", "understanding", "watch",
        "watches", "watched", "watching", "follow", "follows", "followed", "following",
        "stop", "stops", "stopped", "stopping", "create", "creates", "created", "creating",
        "speak", "speaks", "spoke", "speaking", "read", "reads", "read", "reading", "allow",
        "allows", "allowed", "allowing", "add", "adds", "added", "adding", "spend", "spends",
        "spent", "spending", "grow", "grows", "grew", "growing", "open", "opens", "opened",
        "opening", "walk", "walks", "walked", "walking", "win", "wins", "won", "winning",
        "offer", "offers", "offered", "offering", "remember", "remembers", "remembered",
        "remembering", "love", "loves", "loved", "loving", "consider", "considers", "considered",
        "considering", "appear", "appears", "appeared", "appearing", "buy", "buys", "bought",
        "buying", "wait", "waits", "waited", "waiting", "serve", "serves", "served", "serving",
        "die", "dies", "died", "dying", "send", "sends", "sent", "sending", "expect",
        "expects", "expected", "expecting", "build", "builds", "built", "building", "stay",
        "stays", "stayed", "staying", "fall", "falls", "fell", "falling", "cut", "cuts",
        "cutting", "reach", "reaches", "reached", "reaching", "kill", "kills", "killed",
        "killing", "remain", "remains", "remained", "remaining", "suggest", "suggests",
        "suggested", "suggesting", "raise", "raises", "raised", "raising", "pass", "passes",
        "passed", "passing", "sell", "sells", "sold", "selling", "require", "requires",
        "required", "requiring", "report", "reports", "reported", "reporting", "decide",
        "decides", "decided", "deciding", "pull", "pulls", "pulled", "pulling"
    }

    STOPWORDS = frozenset((COMMON_WORDS | _EXTRA_STOPWORDS) - _DOMAIN_WORDS)

    # Process-wide cache of learned keywords (shared by all router instances).
    _cache_lock = threading.Lock()
    _kw_cache: Optional[Dict[str, List[str]]] = None
    _kw_cache_expiry: Optional[datetime] = None
    _base_tokens_cache: Optional[frozenset] = None

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _safe_commit(self) -> bool:
        try:
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"DB commit failed in DynamicRouter: {type(e).__name__}: {e}")
            self._rollback()
            return False

    def _rollback(self):
        try:
            self.db.rollback()
        except Exception:
            pass

    @classmethod
    def _invalidate_cache(cls):
        with cls._cache_lock:
            cls._kw_cache = None
            cls._kw_cache_expiry = None

    @classmethod
    def _base_tokens(cls) -> frozenset:
        """Every word that appears in any base keyword (never learned again)."""
        if cls._base_tokens_cache is None:
            toks = set()
            for kws in cls.BASE_KEYWORDS.values():
                for kw in kws:
                    toks.update(re.findall(r"[a-z]+", kw.lower()))
            cls._base_tokens_cache = frozenset(toks)
        return cls._base_tokens_cache

    @staticmethod
    def _tokenise(message: str) -> List[str]:
        """Alphabetic whole words, 3-20 chars. Skips codes/numbers like WM-001, INV2024."""
        return re.findall(r"\b[a-z]{3,20}\b", (message or "").lower())

    # ------------------------------------------------------------------
    # Keywords
    # ------------------------------------------------------------------

    def _get_learned_keywords(self) -> Dict[str, List[str]]:
        """Get active, confirmed learned keywords from the database (cached)."""
        cls = DynamicRouter
        now = datetime.now(timezone.utc)
        with cls._cache_lock:
            if cls._kw_cache is not None and cls._kw_cache_expiry and now < cls._kw_cache_expiry:
                return cls._kw_cache

        from database import LearnedTriggerKeyword

        try:
            learned = self.db.query(LearnedTriggerKeyword).filter(
                LearnedTriggerKeyword.active == True,  # noqa: E712
                LearnedTriggerKeyword.confidence >= ACTIVE_THRESHOLD,
                LearnedTriggerKeyword.usage_count >= MIN_LEARNED_USES,
            ).all()
        except Exception as e:
            # Routing must keep working on base keywords if the learning table is unavailable
            logger.error(f"Could not load learned keywords: {type(e).__name__}: {e}")
            self._rollback()
            return {}

        keywords_by_agent: Dict[str, List[str]] = {}
        for entry in learned:
            kw = (entry.keyword or "").strip().lower()
            if len(kw) < 3 or entry.agent_type not in cls.BASE_KEYWORDS:
                continue
            keywords_by_agent.setdefault(entry.agent_type, []).append(kw)

        with cls._cache_lock:
            cls._kw_cache = keywords_by_agent
            cls._kw_cache_expiry = now + timedelta(minutes=CACHE_TTL_MINUTES)
        return keywords_by_agent

    def _get_weighted_keywords(self) -> Dict[str, Dict[str, float]]:
        """{agent: {keyword: weight}} combining base and learned keywords."""
        learned = self._get_learned_keywords()
        out: Dict[str, Dict[str, float]] = {}
        for agent_type, base in self.BASE_KEYWORDS.items():
            weights: Dict[str, float] = {}
            for kw in learned.get(agent_type, []):
                weights[kw] = LEARNED_WEIGHT
            for kw in base:
                kw = kw.lower()
                w = WEAK_WEIGHT if kw in self.WEAK_KEYWORDS else 1.0
                weights[kw] = max(weights.get(kw, 0.0), w)
            out[agent_type] = weights
        return out

    def _get_all_keywords(self) -> Dict[str, List[str]]:
        """Get all keywords (base + learned) for each agent."""
        return {a: list(w) for a, w in self._get_weighted_keywords().items()}

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _score_message(self, text: str) -> Dict[str, float]:
        """
        Score each agent. Matches are whole-word; the longest phrase claims its text first
        so overlapping shorter keywords are not double counted. A keyword counts once per
        message no matter how often it appears.
        """
        weighted = self._get_weighted_keywords()

        spans: Dict[Tuple[int, int], List[Tuple[str, str, float]]] = {}
        for agent, kws in weighted.items():
            for kw, w in kws.items():
                for m in _compile_keyword(kw).finditer(text):
                    spans.setdefault((m.start(), m.end()), []).append((agent, kw, w))

        claimed: List[Tuple[int, int]] = []
        matched: Dict[str, Dict[str, float]] = {a: {} for a in weighted}
        for (start, end), entries in sorted(spans.items(), key=lambda kv: (-(kv[0][1] - kv[0][0]), kv[0][0])):
            if any(start < ce and end > cs for cs, ce in claimed):
                continue
            claimed.append((start, end))
            for agent, kw, w in entries:
                matched[agent][kw] = max(matched[agent].get(kw, 0.0), w)

        return {a: round(sum(d.values()), 2) for a, d in matched.items()}

    def detect_agent(
        self,
        message: str,
        method: str = "hybrid"
    ) -> Tuple[str, float, str]:
        """
        Detect which agent should handle the message.

        Args:
            message: The user's message
            method: "keyword" (keywords only), "llm_classify" (LLM only),
                    or "hybrid" (keywords when clear, otherwise the LLM)

        Returns:
            Tuple of (agent_type, confidence, method_used). method_used is what
            actually decided: "keyword", "llm_classify", or a fallback such as
            "keyword_default", "keyword_tie", "keyword_fallback", "empty_message",
            "llm_classify_error", "llm_classify_unrecognised". Fallbacks have
            confidence 0.3, so callers can ask for clarification.
        """
        if method not in ("keyword", "llm_classify", "hybrid"):
            logger.warning(f"Unknown routing method {method!r}; using 'hybrid'")
            method = "hybrid"

        text = re.sub(r"\s+", " ", str(message or "").lower()).strip()
        if not text:
            return "stock_quote", 0.3, "empty_message"

        if method == "llm_classify":
            return self._llm_classify(text)

        scores = self._score_message(text)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)  # stable: ties keep agent order
        top_agent, top = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = round(top - second, 2)
        is_tie = top > 0 and margin == 0
        leader = top_agent if top > 0 else None

        clear = top > 0 and not is_tie
        if method == "hybrid":
            clear = clear and top >= MIN_KEYWORD_SCORE

        if clear:
            confidence = round(min(0.4 + 0.2 * margin, 0.95), 2)
            return top_agent, confidence, "keyword"

        if method == "hybrid":
            result = self._llm_classify(text)
            if result[2] in ("llm_classify_error", "llm_classify_unrecognised") and leader:
                return leader, 0.3, "keyword_fallback"
            return result

        # keyword-only mode with no clear winner
        if is_tie:
            return leader, 0.3, "keyword_tie"
        return "stock_quote", 0.3, "keyword_default"

    def _llm_classify(self, message: str) -> Tuple[str, float, str]:
        """
        Use LLM to classify the message when keywords are missing or ambiguous.

        Returns:
            Tuple of (agent_type, confidence, method)
        """
        from llm_client import get_llm_client

        system_prompt = """You are a message classifier. Identify which agent should handle the message.

Agents:
- order_invoice: Customers, orders, invoices, POs
- stock_quote: Stock, inventory, pricing, quotes
- shipment: Delivery, shipping, pickup, packing
- customer_onboarding: New customers, registration, onboarding
- payment_followup: Payments, receipts, transactions

Return ONLY the agent name (one word)."""

        try:
            llm_client = get_llm_client()
            result = llm_client.chat_completion(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": (message or "")[:2000]}
                ],
                temperature=0,
                max_tokens=20,
                operation="route-classify",
            )
            content = ((result or {}).get("content") or "").lower()
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return "stock_quote", 0.3, "llm_classify_error"

        # Tolerate punctuation, quotes, backticks or a short sentence around the name
        cleaned = re.sub(r"[^a-z_]+", " ", content)
        found = [a for a in self.BASE_KEYWORDS if re.search(rf"(?<![a-z_]){a}(?![a-z_])", cleaned)]
        if len(found) == 1:
            return found[0], 0.6, "llm_classify"

        logger.warning(f"LLM returned an unrecognised agent: {content[:60]!r}")
        return "stock_quote", 0.3, "llm_classify_unrecognised"

    # ------------------------------------------------------------------
    # Logging and feedback
    # ------------------------------------------------------------------

    def log_routing_decision(
        self,
        message: str,
        detected_agent: str,
        confidence: float,
        method: str
    ):
        """
        Log the routing decision for learning.

        Returns the log id (pass it to record_user_feedback), or None if logging failed.
        The message is truncated and emails are masked before storing.
        """
        from database import MessageRoutingLog

        try:
            log_entry = MessageRoutingLog(
                message=_safe_message(message),
                detected_agent=detected_agent,
                confidence=confidence,
                method=method
            )
            self.db.add(log_entry)
            self.db.flush()
            log_id = log_entry.id
        except Exception as e:
            logger.error(f"Could not log routing decision: {type(e).__name__}: {e}")
            self._rollback()
            return None

        return log_id if self._safe_commit() else None

    def record_user_feedback(
        self,
        log_id: str,
        feedback: str,
        correct_agent: Optional[str] = None
    ) -> bool:
        """
        Record user feedback on a routing decision, and learn from it.

        - correct_agent given: keywords of the wrong route are penalised (if it differed)
          and the message is learned for correct_agent.
        - feedback in POSITIVE_FEEDBACK: the message is learned for the detected agent.
        - feedback in NEGATIVE_FEEDBACK (no correct_agent): the detected agent's learned
          keywords on this message are penalised.

        Returns True if the feedback was stored.
        """
        from database import MessageRoutingLog

        try:
            log = self.db.query(MessageRoutingLog).filter(
                MessageRoutingLog.id == log_id
            ).first()
        except Exception as e:
            logger.error(f"Feedback lookup failed: {type(e).__name__}: {e}")
            self._rollback()
            return False

        if not log:
            logger.warning(f"record_user_feedback: no routing log with id {log_id!r}")
            return False

        log.user_feedback = None if feedback is None else str(feedback)[:255]
        if not self._safe_commit():
            return False

        fb = str(feedback or "").strip().lower()
        message, detected = log.message, log.detected_agent

        if correct_agent in self.BASE_KEYWORDS:
            if detected != correct_agent:
                self.penalize_keywords(message, detected)
            self.learn_new_keyword(message, correct_agent)
        elif fb in NEGATIVE_FEEDBACK:
            self.penalize_keywords(message, detected)
        elif fb in POSITIVE_FEEDBACK and detected in self.BASE_KEYWORDS:
            self.learn_new_keyword(message, detected)
        return True

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------

    def _extract_candidates(self, message: str) -> List[str]:
        """Distinct, meaningful words worth learning (no stopwords, base-keyword words or numbers)."""
        base_tokens = self._base_tokens()
        seen, out = set(), []
        for w in self._tokenise(message):
            if w in seen:
                continue
            seen.add(w)
            if w in self.STOPWORDS or w in base_tokens:
                continue
            out.append(w)
            if len(out) >= MAX_CANDIDATE_WORDS:
                break
        return out

    def learn_new_keyword(
        self,
        message: str,
        correct_agent: str,
        confidence: float = INITIAL_CONFIDENCE
    ) -> int:
        """
        Learn keywords from a message that was (confirmed to be) routed correctly.

        New keywords start at INITIAL_CONFIDENCE (a larger `confidence` is capped to it) and
        only become active after MIN_LEARNED_USES confirmed uses at ACTIVE_THRESHOLD.
        At most MAX_NEW_KEYWORDS_PER_MESSAGE new keywords are added per message, and a word
        already strongly tied to a different agent is skipped.

        Returns the number of keyword rows created or reinforced.
        """
        if correct_agent not in self.BASE_KEYWORDS:
            logger.warning(f"learn_new_keyword: unknown agent {correct_agent!r}; nothing learned")
            return 0

        candidates = self._extract_candidates(message)
        if not candidates:
            return 0

        from database import LearnedTriggerKeyword

        start_conf = min(float(confidence), INITIAL_CONFIDENCE)
        touched = 0
        try:
            rows = self.db.query(LearnedTriggerKeyword).filter(
                LearnedTriggerKeyword.keyword.in_(candidates)
            ).all()

            mine = {r.keyword: r for r in rows if r.agent_type == correct_agent}
            claimed_elsewhere = {
                r.keyword for r in rows
                if r.agent_type != correct_agent and r.active and (r.confidence or 0) >= ACTIVE_THRESHOLD
            }

            now = datetime.now(timezone.utc)
            new_rows = 0
            for word in candidates:
                if word in claimed_elsewhere:
                    continue
                row = mine.get(word)
                if row is not None:
                    row.usage_count = func.coalesce(LearnedTriggerKeyword.usage_count, 0) + 1
                    row.success_count = func.coalesce(LearnedTriggerKeyword.success_count, 0) + 1
                    row.confidence = min(round((row.confidence or 0.0) + CONFIDENCE_STEP, 2), 1.0)
                    row.last_used_at = now
                    if not row.active and row.confidence >= ACTIVE_THRESHOLD:
                        row.active = True
                    touched += 1
                elif new_rows < MAX_NEW_KEYWORDS_PER_MESSAGE:
                    self.db.add(LearnedTriggerKeyword(
                        keyword=word,
                        agent_type=correct_agent,
                        confidence=start_conf,
                        usage_count=1,
                        success_count=1,
                    ))
                    new_rows += 1
                    touched += 1
        except Exception as e:
            logger.error(f"learn_new_keyword failed: {type(e).__name__}: {e}")
            self._rollback()
            return 0

        if touched and self._safe_commit():
            self._invalidate_cache()
            return touched
        return 0

    def penalize_keywords(self, message: str, wrong_agent: str) -> int:
        """
        Lower confidence of learned keywords on a message that was misrouted to wrong_agent.
        Keywords falling to DEACTIVATE_AT or below are switched off. Base keywords are untouched.

        Returns the number of keywords penalised.
        """
        tokens = list(set(self._tokenise(message)))
        if not tokens or wrong_agent not in self.BASE_KEYWORDS:
            return 0

        from database import LearnedTriggerKeyword

        try:
            rows = self.db.query(LearnedTriggerKeyword).filter(
                LearnedTriggerKeyword.keyword.in_(tokens),
                LearnedTriggerKeyword.agent_type == wrong_agent,
            ).all()
            for row in rows:
                row.confidence = max(round((row.confidence or 0.0) - PENALTY_STEP, 2), 0.0)
                if row.confidence <= DEACTIVATE_AT:
                    row.active = False
        except Exception as e:
            logger.error(f"penalize_keywords failed: {type(e).__name__}: {e}")
            self._rollback()
            return 0

        if rows and self._safe_commit():
            self._invalidate_cache()
            return len(rows)
        return 0
