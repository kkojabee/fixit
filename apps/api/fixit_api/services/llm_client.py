import os
import json
import logging
import urllib.request
from typing import Optional, Dict, Any, List
from openai import OpenAI, AzureOpenAI
from fixit_api.config import settings

logger = logging.getLogger(__name__)

# Azure OpenAI API Configuration via MSDN Cost Recommendation API
DEFAULT_API_VERSION = "2024-05-01-preview"

def fetch_recommended_azure_config(preferred_model: Optional[str] = None) -> Optional[dict]:
    """
    Dynamically fetch optimal Azure OpenAI URL & Key from msdn-cost recommendation API (ports 8100/8101).
    Prefers gpt-6.1-sol with fallback to other models dynamically returned by recommendation service.
    """
    target = preferred_model or getattr(settings, "DOC_LLM_MODEL", "gpt-6.1-sol")
    
    # Candidate recommendation endpoints
    base_url = getattr(settings, "MSDN_COST_API_URL", "http://192.168.209.120:8100/api/costs/recommendation")
    candidate_urls = [base_url]
    # Add port 8101 fallback if base uses 8100
    if ":8100" in base_url:
        candidate_urls.append(base_url.replace(":8100", ":8101"))
    elif ":8101" in base_url:
        candidate_urls.append(base_url.replace(":8101", ":8100"))

    for url in candidate_urls:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    if "url" in data and "key" in data:
                        models_str = data.get("models", "")
                        if "gpt-6.1-sol" in models_str:
                            chosen_model = "gpt-6.1-sol"
                        elif target in models_str:
                            chosen_model = target
                        elif "gpt-6-luna" in models_str:
                            chosen_model = "gpt-6-luna"
                        elif "gpt-5.6-luna" in models_str:
                            chosen_model = "gpt-5.6-luna"
                        else:
                            chosen_model = target

                        logger.info(f"[msdn-cost] Connected Azure OpenAI via {url}: {data['url']} [Model: {chosen_model}]")
                        return {
                            "endpoint": data["url"],
                            "key": data["key"],
                            "model": chosen_model,
                            "api_version": DEFAULT_API_VERSION
                        }
        except Exception as e:
            logger.debug(f"[msdn-cost] Check failed for {url}: {e}")
            continue

    logger.error("[msdn-cost] Recommendation API unreachable on all candidate endpoints. Azure OpenAI credentials unavailable.")
    return None


class FixitLLMClient:
    """Manages Azure OpenAI client with Medium Thinking support for image recognition fallback."""

    @classmethod
    def get_azure_client(cls, model_name: Optional[str] = None) -> Optional[tuple[AzureOpenAI, str]]:
        cfg = fetch_recommended_azure_config(preferred_model=model_name)
        if not cfg:
            return None
        try:
            client = AzureOpenAI(
                azure_endpoint=cfg["endpoint"],
                api_key=cfg["key"],
                api_version=cfg["api_version"],
                timeout=180.0
            )
            return client, cfg["model"]
        except Exception as e:
            logger.error(f"[AzureOpenAI] Client init failed: {e}")
            return None

    @classmethod
    def query_azure_vision(
        cls,
        image_b64: str,
        prompt: str,
        reasoning_effort: str = "low"
    ) -> Optional[str]:
        """
        Sends One-Pass Vision request to Azure gpt-6.1-sol with high context length
        """
        client_tuple = cls.get_azure_client(model_name="gpt-6.1-sol")
        if not client_tuple:
            return None
        
        client, model = client_tuple
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}",
                            "detail": "high"
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]

        kwargs = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": 8000
        }

        effort = reasoning_effort or getattr(settings, "LLM_REASONING_EFFORT", "low")
        if effort and str(effort).lower() not in ("none", "off", "disable", "false"):
            kwargs["reasoning_effort"] = str(effort).lower()

        try:
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content
        except Exception as e:
            err_msg = str(e).lower()
            logger.warning(f"[AzureOpenAI] Vision request failed with params: {e}. Retrying without reasoning_effort...")
            if "reasoning_effort" in err_msg or "extra parameter" in err_msg or "unsupported" in err_msg:
                kwargs.pop("reasoning_effort", None)
                if "max_completion_tokens" in err_msg:
                    kwargs["max_tokens"] = kwargs.pop("max_completion_tokens", 8000)
                try:
                    resp = client.chat.completions.create(**kwargs)
                    return resp.choices[0].message.content
                except Exception as retry_err:
                    logger.error(f"[AzureOpenAI] Retry without reasoning_effort failed: {retry_err}")
            return None
