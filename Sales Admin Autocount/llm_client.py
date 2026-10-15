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
        self.model = settings.ilmu_model
        self.vision_model = getattr(settings, "ilmu_vision_model", "")
        self.use_gateway = bool(settings.llm_gateway_url)
        if self.use_gateway:
            # The gateway holds the provider keys (incl. vision) and meters usage per client key.
            self.client = OpenAI(base_url=settings.llm_gateway_url, api_key=settings.llm_gateway_key)
            self.vision_client = self.client
        else:
            self.client = OpenAI(base_url=settings.ilmu_base_url, api_key=settings.ilmu_api_key)
            # Vision calls may use a different API key
            vision_key = getattr(settings, "ilmu_vision_key", "") or settings.ilmu_api_key
            self.vision_client = OpenAI(base_url=settings.ilmu_base_url, api_key=vision_key)

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make a chat completion request to Ilmu Claw.

        Args:
            messages: List of message dicts with 'role' and 'content'. For
                vision calls, 'content' may be a list of text/image_url parts.
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            model: Override the configured model (e.g. the vision model for OCR)
            operation: Usage tag for the LLM gateway (e.g. "email-order-extraction"), shown in billing data
            **kwargs: Additional parameters for the API call

        Returns:
            Dict containing response, input_tokens, output_tokens, cached_input_tokens, model (cost and budgets are tracked by the LLM gateway)
        """
        used_model = model or self.model
        # Vision model may need its own credentials
        client = self.vision_client if (used_model == self.vision_model and self.vision_model) else self.client
        if self.use_gateway:
            extra_body = dict(kwargs.pop("extra_body", None) or {})
            metadata = dict(extra_body.get("metadata") or {})
            metadata["tags"] = list(metadata.get("tags") or []) + ["app:sales-autocount", f"op:{operation or 'chat'}"]
            extra_body["metadata"] = metadata
            kwargs["extra_body"] = extra_body
        response = client.chat.completions.create(
            model=used_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        # Extract usage information
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        cached_input_tokens = (getattr(details, "cached_tokens", None) if details else None) or 0

        return {
            "content": response.choices[0].message.content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_input_tokens": cached_input_tokens,
            "total_tokens": input_tokens + output_tokens,
            "model": used_model
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

        result = self.chat_completion(messages, operation="pdf-extraction")
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

        result = self.chat_completion(messages, operation="draft-message")
        return result


# Global LLM client instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create the global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
