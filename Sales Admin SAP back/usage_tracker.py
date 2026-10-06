from typing import Optional
from datetime import datetime, date, timezone
from sqlalchemy.orm import Session
from database import UsageLogEntry, get_sessionmaker
from config import settings
from enum import Enum


class BudgetStatus(str, Enum):
    """Status for budget check results."""
    PASSED = "passed"
    EXCEEDED = "exceeded"
    COST_ALERT = "cost_alert"


class UsageTracker:
    """
    Tracks token usage and enforces budget limits.
    Logs every LLM call and enforces per-day/per-month budget stoppers.
    """

    def __init__(self, session: Session):
        self.session = session
        self.daily_budget = settings.token_budget_per_day
        self.monthly_budget = settings.token_budget_per_month
        self.cost_alert_threshold = settings.cost_alert_threshold_usd

    def record_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        agent_name: str,
        operation_type: str,
        cost_usd: Optional[float] = None,
        model: str = "unknown"
    ) -> UsageLogEntry:
        """
        Record token usage for an LLM call.
        If cost_usd is not provided, it is calculated from the pricing table
        in config (settings.calculate_llm_cost).
        """
        if cost_usd is None:
            cost_usd = settings.calculate_llm_cost(input_tokens, output_tokens, model)

        entry = UsageLogEntry(
            date=date.today(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            agent_name=agent_name,
            operation_type=operation_type,
            model=model
        )

        self.session.add(entry)
        self.session.commit()
        return entry

    def check_budget(self) -> tuple[BudgetStatus, str]:
        """
        Check if token usage is within budget limits.
        Returns (status: BudgetStatus, message: str).
        """
        today = date.today()
        current_month = today.replace(day=1)

        # Get today's usage
        daily_usage = self.session.query(UsageLogEntry).filter(
            UsageLogEntry.date == today
        ).all()

        daily_tokens = sum(u.input_tokens + u.output_tokens for u in daily_usage)
        daily_cost = sum(u.cost_usd for u in daily_usage)

        # Get this month's usage
        monthly_usage = self.session.query(UsageLogEntry).filter(
            UsageLogEntry.date >= current_month
        ).all()

        monthly_tokens = sum(u.input_tokens + u.output_tokens for u in monthly_usage)
        monthly_cost = sum(u.cost_usd for u in monthly_usage)

        # Check daily budget
        if daily_tokens >= self.daily_budget:
            return BudgetStatus.EXCEEDED, f"Daily token budget exceeded: {daily_tokens}/{self.daily_budget} tokens"

        # Check monthly budget
        if monthly_tokens >= self.monthly_budget:
            return BudgetStatus.EXCEEDED, f"Monthly token budget exceeded: {monthly_tokens}/{self.monthly_budget} tokens"

        # Check cost alert threshold
        if daily_cost >= self.cost_alert_threshold or monthly_cost >= self.cost_alert_threshold:
            return BudgetStatus.COST_ALERT, f"Cost alert: Daily ${daily_cost:.2f} / Monthly ${monthly_cost:.2f} exceeds threshold ${self.cost_alert_threshold:.2f}"

        return BudgetStatus.PASSED, "Budget check passed"

    def get_daily_usage(self, target_date: Optional[date] = None) -> dict:
        """Get usage summary for a specific day (defaults to today)."""
        target_date = target_date or date.today()

        usage = self.session.query(UsageLogEntry).filter(
            UsageLogEntry.date == target_date
        ).all()

        return {
            "date": target_date,
            "total_tokens": sum(u.input_tokens + u.output_tokens for u in usage),
            "input_tokens": sum(u.input_tokens for u in usage),
            "output_tokens": sum(u.output_tokens for u in usage),
            "total_cost_usd": sum(u.cost_usd for u in usage),
            "num_calls": len(usage),
            "by_agent": self._usage_by_agent(usage),
            "by_model": self._usage_by_model(usage)
        }

    def get_monthly_usage(self, target_month: Optional[date] = None) -> dict:
        """Get usage summary for a specific month (defaults to current month)."""
        from calendar import monthrange

        target_month = target_month or date.today().replace(day=1)

        # Calculate the last day of the target month
        _, last_day = monthrange(target_month.year, target_month.month)
        month_end = target_month.replace(day=last_day)

        usage = self.session.query(UsageLogEntry).filter(
            UsageLogEntry.date >= target_month,
            UsageLogEntry.date <= month_end
        ).all()

        return {
            "month": target_month,
            "total_tokens": sum(u.input_tokens + u.output_tokens for u in usage),
            "input_tokens": sum(u.input_tokens for u in usage),
            "output_tokens": sum(u.output_tokens for u in usage),
            "total_cost_usd": sum(u.cost_usd for u in usage),
            "num_calls": len(usage),
            "by_agent": self._usage_by_agent(usage),
            "by_model": self._usage_by_model(usage)
        }

    def _usage_by_agent(self, usage: list[UsageLogEntry]) -> dict:
        """Aggregate usage by agent name."""
        by_agent = {}
        for u in usage:
            if u.agent_name not in by_agent:
                by_agent[u.agent_name] = {
                    "total_tokens": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_cost_usd": 0.0,
                    "num_calls": 0
                }
            by_agent[u.agent_name]["total_tokens"] += u.input_tokens + u.output_tokens
            by_agent[u.agent_name]["input_tokens"] += u.input_tokens
            by_agent[u.agent_name]["output_tokens"] += u.output_tokens
            by_agent[u.agent_name]["total_cost_usd"] += u.cost_usd
            by_agent[u.agent_name]["num_calls"] += 1
        return by_agent

    def _usage_by_model(self, usage: list[UsageLogEntry]) -> dict:
        """Aggregate usage by LLM model."""
        by_model = {}
        for u in usage:
            model = u.model or "unknown"
            if model not in by_model:
                by_model[model] = {
                    "total_tokens": 0,
                    "total_cost_usd": 0.0,
                    "num_calls": 0
                }
            by_model[model]["total_tokens"] += u.input_tokens + u.output_tokens
            by_model[model]["total_cost_usd"] += u.cost_usd
            by_model[model]["num_calls"] += 1
        return by_model

    def get_remaining_budget(self) -> dict:
        """Get remaining budget for today and this month."""
        today = date.today()
        current_month = today.replace(day=1)

        daily_usage = self.get_daily_usage(today)
        monthly_usage = self.get_monthly_usage(current_month)

        return {
            "daily_remaining_tokens": max(0, self.daily_budget - daily_usage["total_tokens"]),
            "daily_budget": self.daily_budget,
            "daily_used_tokens": daily_usage["total_tokens"],
            "monthly_remaining_tokens": max(0, self.monthly_budget - monthly_usage["total_tokens"]),
            "monthly_budget": self.monthly_budget,
            "monthly_used_tokens": monthly_usage["total_tokens"]
        }
