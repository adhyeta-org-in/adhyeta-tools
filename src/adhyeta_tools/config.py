import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    # reader
    proof_host = "127.0.0.1"
    proof_port = 5003

    # llm-serve
    llm_host = "127.0.0.1"
    llm_port = 5001
    model_path = "/path/to/your/model.gguf"
    mmproj_path = "/path/to/your/mmproj.gguf"
    device = "Vulkan0"

    # llm-ocr
    prompt = (
        "Extract all text from this page. Sanskrit (in Devanagari script) as well as English etc. Ignore all pictures."
    )


def load_config() -> Config:
    xdg_config_dir = Path(os.environ["XDG_CONFIG_HOME"]) / "adhyeta"
    dotenv_toml_path = Path(os.path.dirname(__file__)).parent / ".env"
    config_toml = xdg_config_dir / "tools.config.toml"
    path = dotenv_toml_path if dotenv_toml_path.exists() else config_toml

    if not dotenv_toml_path.exists() and not config_toml.exists():
        xdg_config_dir.mkdir(parents=True, exist_ok=True)
        config_toml.write_text(
            f"""[proof]
host = "{Config.proof_host}"
port = {Config.proof_port}

[llm-serve]
host = "{Config.llm_host}"
port = {Config.llm_port}
model_path = "{Config.model_path}"
mmproj_path = "{Config.mmproj_path}"
device = "{Config.device}"

[llm-ocr]
prompt = "{Config.prompt}"
""",
            encoding="utf-8",
        )

    with path.open("rb") as f:
        data = tomllib.load(f)

    cfg = Config()

    cfg.proof_host = data["proof"]["host"]
    cfg.proof_port = data["proof"]["port"]

    serve = data["llm-serve"]
    cfg.llm_host = serve["host"]
    cfg.llm_port = serve["port"]
    cfg.model_path = serve["model_path"]
    cfg.mmproj_path = serve["mmproj_path"]
    cfg.device = serve["device"]

    cfg.prompt = data["llm-ocr"]["prompt"]

    return cfg
