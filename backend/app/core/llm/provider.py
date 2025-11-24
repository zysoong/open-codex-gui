"""LLM provider abstraction using LiteLLM."""

import os
from typing import List, Dict, Any, AsyncIterator, Optional
from litellm import acompletion
import litellm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Disable LiteLLM logging by default
litellm.suppress_debug_info = True


class LLMProvider:
    """LLM provider using LiteLLM for unified API access."""

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4",
        api_key: str | None = None,
        **config
    ):
        """
        Initialize LLM provider.

        Args:
            provider: Provider name (openai, anthropic, azure, etc.)
            model: Model name
            api_key: API key for the provider
            **config: Additional configuration (temperature, max_tokens, etc.)
        """
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.config = config

        # Set API key in environment if provided
        if api_key:
            self._set_api_key(provider, api_key)

    def _set_api_key(self, provider: str, api_key: str):
        """Set API key in environment based on provider."""
        key_mapping = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "azure": "AZURE_API_KEY",
            "cohere": "COHERE_API_KEY",
            "huggingface": "HUGGINGFACE_API_KEY",
        }

        env_key = key_mapping.get(provider.lower())
        if env_key:
            os.environ[env_key] = api_key

    def _build_model_name(self) -> str:
        """Build the full model name for LiteLLM.

        For most providers, LiteLLM uses format: provider/model
        For OpenAI, just the model name is fine.
        """
        if self.provider.lower() == "openai":
            return self.model
        return f"{self.provider}/{self.model}"

    async def generate(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
        **kwargs
    ) -> Any:
        """
        Generate completion from LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream: Whether to stream the response
            **kwargs: Additional parameters for the completion

        Returns:
            Completion response or async iterator if streaming
        """
        # Merge config with kwargs
        params = {**self.config, **kwargs}

        model_name = self._build_model_name()

        try:
            response = await acompletion(
                model=model_name,
                messages=messages,
                stream=stream,
                **params
            )

            return response

        except Exception as e:
            raise Exception(f"LLM generation failed: {str(e)}")

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any | None]] = None,
        **kwargs
    ) -> AsyncIterator[str | Dict[str, Any]]:
        """
        Generate streaming completion from LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tools for function calling
            **kwargs: Additional parameters for the completion

        Yields:
            Text chunks as they arrive, or function call dicts
        """
        print(f"\n[LLM PROVIDER] generate_stream() called")
        print(f"  Provider: {self.provider}")
        print(f"  Model: {self.model}")
        print(f"  Has API key: {self.api_key is not None}")
        print(f"  Tools count: {len(tools) if tools else 0}")
        print(f"  Messages count: {len(messages)}")

        params = {**self.config, **kwargs}
        model_name = self._build_model_name()
        print(f"  Full model name: {model_name}")

        # Add tools to params if provided
        if tools:
            params['tools'] = tools
            params['tool_choice'] = 'auto'
            print(f"  Tool choice: auto")

        try:
            print(f"[LLM PROVIDER] Calling acompletion...")
            response = await acompletion(
                model=model_name,
                messages=messages,
                stream=True,
                **params
            )

            print(f"[LLM PROVIDER] Stream started, processing chunks...")
            chunk_num = 0
            async for chunk in response:
                chunk_num += 1
                # Extract content from the chunk
                if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta

                    # Handle text content
                    if hasattr(delta, 'content') and delta.content:
                        if chunk_num <= 3:
                            print(f"[LLM PROVIDER] Text chunk #{chunk_num}: {delta.content[:30]}...")
                        yield delta.content

                    # Handle function calls
                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                        print(f"[LLM PROVIDER] Tool call chunk: {delta.tool_calls}")
                        for tool_call in delta.tool_calls:
                            if hasattr(tool_call, 'function'):
                                yield {
                                    "function_call": {
                                        "name": tool_call.function.name,
                                        "arguments": tool_call.function.arguments,
                                    },
                                    "index": tool_call.index if hasattr(tool_call, 'index') else 0,
                                }

            print(f"[LLM PROVIDER] Stream complete. Total chunks: {chunk_num}")

        except Exception as e:
            print(f"[LLM PROVIDER] ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            raise Exception(f"LLM streaming failed: {str(e)}")


def create_llm_provider(
    provider: str,
    model: str,
    llm_config: Dict[str, Any],
    api_key: str | None = None
) -> LLMProvider:
    """
    Factory function to create LLM provider.

    Args:
        provider: Provider name
        model: Model name
        llm_config: LLM configuration dict
        api_key: Optional API key

    Returns:
        LLMProvider instance
    """
    return LLMProvider(
        provider=provider,
        model=model,
        api_key=api_key,
        **llm_config
    )


async def create_llm_provider_with_db(
    provider: str,
    model: str,
    llm_config: Dict[str, Any],
    db: AsyncSession,
    api_key: Optional[str] = None
) -> LLMProvider:
    """
    Factory function to create LLM provider with database API key lookup.

    Priority order:
    1. Explicitly provided api_key parameter
    2. API key from database
    3. Environment variable (fallback)

    Args:
        provider: Provider name
        model: Model name
        llm_config: LLM configuration dict
        db: Database session
        api_key: Optional explicit API key (highest priority)

    Returns:
        LLMProvider instance
    """
    # If API key explicitly provided, use it
    if api_key:
        return LLMProvider(
            provider=provider,
            model=model,
            api_key=api_key,
            **llm_config
        )

    # Try to get API key from database
    try:
        from app.models.database import ApiKey
        from app.core.security.encryption import get_encryption_service
        from datetime import datetime

        # FUTURE: Add .where(ApiKey.user_id == current_user.id)
        query = select(ApiKey).where(ApiKey.provider == provider.lower())
        result = await db.execute(query)
        key_record = result.scalar_one_or_none()

        if key_record:
            # Decrypt the API key
            encryption_service = get_encryption_service()
            decrypted_key = encryption_service.decrypt(key_record.encrypted_key)

            # Update last_used_at timestamp
            key_record.last_used_at = datetime.utcnow()
            await db.commit()

            return LLMProvider(
                provider=provider,
                model=model,
                api_key=decrypted_key,
                **llm_config
            )
    except Exception as e:
        # Log the error but don't fail - fall back to environment variables
        print(f"Warning: Failed to retrieve API key from database: {e}")

    # Fallback to environment variable (original behavior)
    return LLMProvider(
        provider=provider,
        model=model,
        api_key=None,  # Will use environment variable
        **llm_config
    )
