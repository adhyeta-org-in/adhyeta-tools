# Adhyeta Tools

This project provides various tools used for proofreading and other activities.

## llm-proof

Contains the following tools.

`extract-pdf` extracts flattened images from a given pdf file

`start-llamacpp` starts a llama-cpp server using provided parameters.

`start-ocr` performs OCR of the extracted images using a model running on llama-cpp.

`start-reader` opens a proofreader UI in your browser.

In each of the tools, look at the `TUNABLE CONFIG` section to modify stuff that cannot be tuned via the cli.
