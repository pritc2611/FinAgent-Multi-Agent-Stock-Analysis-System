from langchain_huggingface import HuggingFaceEndpoint , ChatHuggingFace
from core.config import settings
from langchain_nvidia_ai_endpoints import ChatNVIDIA

def get_llm(bind_tools: list | None = None) -> HuggingFaceEndpoint:
    """
    Return a configured ChatAnthropic instance.

    Parameters
    ----------
    bind_tools : list of LangChain-compatible tool objects
        When provided, the LLM is returned with tools bound so it can
        call them autonomously during inference.
    """
    if not settings.NVIDIA_API_KEY:
        raise EnvironmentError(
            "API_KEY is missing. Set it in your .env file."
        )
    
    Chat_llm = ChatNVIDIA(
        model="mistralai/devstral-2-123b-instruct-2512",
        nvidia_api_key=settings.NVIDIA_API_KEY, 
        temperature=settings.llm_temperature,
        top_p=0.95,
        max_completion_tokens=settings.llm_max_tokens)

    if bind_tools:
        return Chat_llm.bind_tools(bind_tools)

    return Chat_llm

