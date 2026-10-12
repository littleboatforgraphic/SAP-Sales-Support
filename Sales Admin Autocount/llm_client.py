"""
LLM Client wrapper for Ilmu Claw API (OpenAI-compatible).
Provides a simple interface for agents to make LLM calls.
"""
from openai import OpenAI
from config import settings
from typing import List, Dict, Any, Optional


class LLMClient:
    """Wrapper for Ilmu Claw API using OpenAI SDK."""

    def __init__(self):
        self.client = OpenAI(
            base_url=settings.ilmu_base_url,
            api_key=settings.ilmu_api_key,
        )
        self.model = settings.ilmu_model

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make a chat completion request to Ilmu Claw.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters for the API call

        Returns:
            Dict containing response, input_tokens, output_tokens, cost
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        # Extract usage information
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        # Cost calculated from the pricing table in config (settings.calculate_llm_cost)
        cost = settings.calculate_llm_cost(input_tokens, output_tokens, self.model)

        return {
            "content": response.choices[0].message.content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": cost,
            "model": self.model
        }

    def extract_text_from_pdf(
        self,
        pdf_content: bytes,
        extraction_prompt: str
    ) -> Dict[str, Any]:
        """
        Extract structured text from PDF using Ilmu Claw.

        Args:
            pdf_content: Raw bytes of the PDF file
            extraction_prompt: Instructions for what to extract

        Returns:
            Dict containing extracted data and token usage
        """
        # Note: Ilmu Claw may support file uploads. If not, this needs to be adapted.
        # This is a placeholder - check Ilmu Claw documentation for PDF processing.

        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that extracts structured data from documents."
            },
            {
                "role": "user",
                "content": f"{extraction_prompt}\n\nHere is the document content:"
            }
        ]

        # If Ilmu Claw supports file uploads, include the PDF here
        # For now, this is a placeholder - you may need to convert PDF to text first
        # or use a different approach based on Ilmu Claw's capabilities

        result = self.chat_completion(messages)
        return result

    def draft_message(
        self,
        context: str,
        task: str,
        tone: str = "professional"
    ) -> Dict[str, Any]:
        """
        Draft a message based on context and task.

        Args:
            context: Background information for the message
            task: What the message should accomplish
            tone: Desired tone (professional, casual, etc.)

        Returns:
            Dict containing drafted message and token usage
        """
        messages = [
            {
                "role": "system",
                "content": f"You are a professional assistant drafting business messages. Use a {tone} tone."
            },
            {
                "role": "user",
                "content": f"Context: {context}\n\nTask: {task}\n\nDraft the message:"
            }
        ]

        result = self.chat_completion(messages)
        return result


# Global LLM client instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create the global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
