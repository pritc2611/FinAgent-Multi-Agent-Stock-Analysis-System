from langchain_huggingface import HuggingFaceEndpoint , ChatHuggingFace
from core.config import settings


def get_llm(bind_tools: list | None = None) -> HuggingFaceEndpoint:
    """
    Return a configured ChatAnthropic instance.

    Parameters
    ----------
    bind_tools : list of LangChain-compatible tool objects
        When provided, the LLM is returned with tools bound so it can
        call them autonomously during inference.
    """
    if not settings.api_key:
        raise EnvironmentError(
            "API_KEY is missing. Set it in your .env file."
        )

    Chatllm = HuggingFaceEndpoint(
        repo_id=settings.llm_model,
        temperature=settings.llm_temperature,
        max_new_tokens=settings.llm_max_tokens,
        huggingfacehub_api_token=settings.api_key,
    )

    llm = ChatHuggingFace(llm=Chatllm)
    if bind_tools:
        return llm.bind_tools(bind_tools)

    return llm
