from server.config import ServerConfig


def test_agent_llm_config_falls_back_to_main_llm_config():
    config = ServerConfig(
        llm_api_key="main-key",
        llm_base_url="https://main.example/v1",
        llm_model="main-model",
        agent_llm_model="",
    )

    assert config.resolved_agent_llm_api_key == "main-key"
    assert config.resolved_agent_llm_base_url == "https://main.example/v1"
    assert config.resolved_agent_llm_model == "main-model"


def test_agent_llm_config_uses_agent_specific_values():
    config = ServerConfig(
        llm_api_key="main-key",
        llm_base_url="https://main.example/v1",
        llm_model="main-model",
        agent_llm_api_key="agent-key",
        agent_llm_base_url="https://agent.example/v1",
        agent_llm_model="agent-model",
    )

    assert config.resolved_agent_llm_api_key == "agent-key"
    assert config.resolved_agent_llm_base_url == "https://agent.example/v1"
    assert config.resolved_agent_llm_model == "agent-model"
