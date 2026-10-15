"""
Dynamic learning system for agent routing and trigger detection.

This module learns from user interactions to:
1. Improve routing accuracy between agents
2. Detect new trigger keywords automatically
3. Adapt to user behavior patterns
"""

import logging
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
import re

logger = logging.getLogger(__name__)


class DynamicRouter:
    """Dynamic routing system that learns from user interactions."""

    # Base keywords for each agent (hardcoded defaults)
    BASE_KEYWORDS = {
        "order_invoice": [
            "customer", "client", "debtor", "300-a", "abc trading", "xyz construction", "buildwell",
            "order", "invoice", "po", "purchase order", "sales order"
        ],
        "stock_quote": [
            "stock", "quote", "quotation", "price", "inventory", "available", "wm-", "brc-", "weld"
        ],
        "shipment": [
            "shipment", "delivery", "deliver", "ship", "pickup", "pack"
        ],
        "customer_onboarding": [
            "new customer", "customer onboarding", "register", "onboard", "new account"
        ],
        "payment_followup": [
            "payment", "paid", "receipt", "transaction", "bank"
        ]
    }

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

    def __init__(self, db: Session):
        self.db = db
        self._learned_keywords_cache = None
        self._cache_expiry = None

    def _get_learned_keywords(self) -> Dict[str, List[str]]:
        """Get learned keywords from database with caching."""
        from database import LearnedTriggerKeyword

        # Simple cache - expires after 5 minutes
        if self._learned_keywords_cache and self._cache_expiry:
            from datetime import datetime, timezone, timedelta
            if datetime.now(timezone.utc) < self._cache_expiry:
                return self._learned_keywords_cache

        # Fetch from database
        learned = self.db.query(LearnedTriggerKeyword).filter(
            LearnedTriggerKeyword.active == True,
            LearnedTriggerKeyword.confidence >= 0.7  # Only use high-confidence keywords
        ).all()

        # Group by agent type
        keywords_by_agent = {}
        for entry in learned:
            if entry.agent_type not in keywords_by_agent:
                keywords_by_agent[entry.agent_type] = []
            keywords_by_agent[entry.agent_type].append(entry.keyword.lower())

        self._learned_keywords_cache = keywords_by_agent
        from datetime import datetime, timezone, timedelta
        self._cache_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)

        return keywords_by_agent

    def detect_agent(
        self,
        message: str,
        method: str = "hybrid"
    ) -> Tuple[str, float, str]:
        """
        Detect which agent should handle the message.

        Args:
            message: The user's message
            method: "keyword", "llm_classify", or "hybrid"

        Returns:
            Tuple of (agent_type, confidence, method_used)
        """
        message_lower = message.lower().strip()

        # Get all keywords (base + learned)
        all_keywords = self._get_all_keywords()

        # Score each agent based on keyword matches
        scores = {}
        for agent_type, keywords in all_keywords.items():
            score = 0
            for keyword in keywords:
                if keyword in message_lower:
                    score += 1
            scores[agent_type] = score

        # Find the agent with highest score
        if scores:
            max_score = max(scores.values())
            if max_score > 0:
                best_agent = max(scores, key=scores.get)
                confidence = min(max_score / 3.0, 1.0)  # Normalize to 0-1
                return best_agent, confidence, method

        # No keywords matched, use LLM classification
        if method == "hybrid":
            return self._llm_classify(message)

        # Default to stock_quote
        return "stock_quote", 0.5, method

    def _get_all_keywords(self) -> Dict[str, List[str]]:
        """Get all keywords (base + learned) for each agent."""
        all_keywords = {}
        learned = self._get_learned_keywords()

        for agent_type in self.BASE_KEYWORDS:
            all_keywords[agent_type] = self.BASE_KEYWORDS[agent_type].copy()
            if agent_type in learned:
                all_keywords[agent_type].extend(learned[agent_type])

        return all_keywords

    def _llm_classify(self, message: str) -> Tuple[str, float, str]:
        """
        Use LLM to classify the message when no keywords match.

        Returns:
            Tuple of (agent_type, confidence, "llm_classify")
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
                    {"role": "user", "content": message}
                ],
                temperature=0.3,
                max_tokens=20
            )
            
            classified = result["content"].strip().lower()
            
            # Map to known agent types
            agent_mapping = {
                "order_invoice": "order_invoice",
                "stock_quote": "stock_quote",
                "shipment": "shipment",
                "customer_onboarding": "customer_onboarding",
                "payment_followup": "payment_followup"
            }
            
            return agent_mapping.get(classified, "stock_quote"), 0.6, "llm_classify"
            
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return "stock_quote", 0.5, "llm_classify_error"

    def log_routing_decision(
        self,
        message: str,
        detected_agent: str,
        confidence: float,
        method: str
    ):
        """Log the routing decision for learning."""
        from database import MessageRoutingLog

        log_entry = MessageRoutingLog(
            message=message,
            detected_agent=detected_agent,
            confidence=confidence,
            method=method
        )
        self.db.add(log_entry)
        self.db.commit()

    def record_user_feedback(
        self,
        log_id: str,
        feedback: str
    ):
        """Record user feedback on routing decision."""
        from database import MessageRoutingLog

        log = self.db.query(MessageRoutingLog).filter(
            MessageRoutingLog.id == log_id
        ).first()

        if log:
            log.user_feedback = feedback
            self.db.commit()

    def learn_new_keyword(
        self,
        message: str,
        correct_agent: str,
        confidence: float = 0.8
    ):
        """
        Learn a new keyword from a correctly routed message.

        Extracts potential keywords from the message and adds them to the learned keywords.
        """
        from database import LearnedTriggerKeyword

        # Extract potential keywords (words, short phrases)
        words = re.findall(r'\b\w+\b', message.lower())
        
        # Filter out common words and short words
        filtered_words = [
            word for word in words
            if word not in self.COMMON_WORDS and len(word) >= 3
        ]
        
        # Add words as potential keywords
        for word in filtered_words:
            # Check if already exists
            existing = self.db.query(LearnedTriggerKeyword).filter(
                LearnedTriggerKeyword.keyword == word,
                LearnedTriggerKeyword.agent_type == correct_agent
            ).first()
            
            if existing:
                # Update existing
                existing.usage_count += 1
                existing.success_count += 1
                # Gradually increase confidence
                existing.confidence = min(existing.confidence + 0.05, 1.0)
                from datetime import datetime, timezone
                existing.last_used_at = datetime.now(timezone.utc)
            else:
                # Create new
                new_keyword = LearnedTriggerKeyword(
                    keyword=word,
                    agent_type=correct_agent,
                    confidence=confidence,
                    usage_count=1,
                    success_count=1
                )
                self.db.add(new_keyword)
        
        self.db.commit()
        
        # Clear cache to force reload
        self._learned_keywords_cache = None
        self._cache_expiry = None
