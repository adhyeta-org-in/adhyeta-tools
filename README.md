# Adhyeta Tools

This project provides various tools used for proofreading and other activities.

## Installation

- Clone the repo
- Install `uv` (https://docs.astral.sh/uv/)
- Install `adhyeta-tools` using `uv tool install --editable .`
- This should give you access to the `adhyeta-tools` command globally depending on how your PATH is set up.
- **Note**: The tool presumes a Linux environment.
- **Note**: llama-cpp (https://github.com/ggml-org/llama.cpp) must be installed on your system to make use of the OCR capabilities.

## Available Tools

`extract` extracts flattened images from a given pdf file

`llm serve` starts a llama-cpp server using provided parameters.

`llm ocr` performs OCR of the extracted images using a model running on llama-cpp.

`proof` opens a proofreader UI in your browser.

The app creates a `$XDG_CONFIG_HOME/adhyeta/tools.config.toml` file on startup with default values. Change them according to your environment.
