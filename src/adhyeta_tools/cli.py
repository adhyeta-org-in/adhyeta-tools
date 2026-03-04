import argparse
import sys
from pathlib import Path

from adhyeta_tools.config import load_config


def add_parser(sub, name: str, help: str):
    return sub.add_parser(name=name, description=help, help=help)


def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Adhyeta Tools: Simple LLM-assisted tooling for proofreading texts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    proof = add_parser(subparsers, "proof", "Proofreader")
    proof.add_argument("project", type=Path, help="Path to project directory")

    extract = add_parser(subparsers, "extract", "PDF to optimized PNGs for OCR")
    extract.add_argument("input", type=Path, help="Input PDF file")
    extract.add_argument("--dpi", type=int, default=300, help="DPI for rendering (default: 300)")
    extract.add_argument(
        "--max-width",
        type=int,
        default=1536,
        help="Maximum output width in pixels (default: 1536)",
    )
    extract.add_argument(
        "--crop",
        type=int,
        default=0,
        help="Margin to crop in pixels (default: 0)",
    )
    extract.add_argument(
        "--simple",
        action="store_true",
        help="Use `simple` mode",
    )
    extract.add_argument("--skip", default="", help="Pages to skip: '1,3-5,10,37-' (1-based)")

    llm = add_parser(subparsers, "llm", "LLM-related operations (choose a subcommand)")
    llm_sub = llm.add_subparsers(dest="llm_command", required=True)

    ocr = add_parser(llm_sub, "ocr", "Perform OCR")
    ocr.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Number of parallel threads (default: 4)",
    )

    ocr.add_argument(
        "--input-dir",
        required=True,
        type=str,
        help="Directory where images are stored",
    )

    ocr.add_argument(
        "--output-dir",
        required=True,
        type=str,
        help="Directory where text files will be stored",
    )

    ocr.add_argument(
        "--prompt",
        type=str,
        help="Optioinal prompt. Overrides the one specified in the config file",
    )

    serve = add_parser(llm_sub, "serve", "Launch llama-server with adjustable settings")
    serve.add_argument("--parallel", type=int, default=4, help="Number of parallel slots (default: 4)")
    serve.add_argument(
        "--batch-size",
        type=int,
        default=1024,
        help="Batch size for prompt processing (default: 1024)",
    )
    serve.add_argument(
        "--ctx-size-per",
        type=int,
        default=8192,
        help="Context size per slot (default: 8192)",
    )

    args = parser.parse_args()

    if args.command == "proof":
        from adhyeta_tools.proof import process

        return process(args.project.resolve(), cfg)
    elif args.command == "extract":
        from adhyeta_tools.pdf_extract import process

        return process(args)
    elif args.command == "llm":
        if args.llm_command == "ocr":
            from adhyeta_tools.llm_ocr import process

            return process(args, cfg)
        elif args.llm_command == "serve":
            from adhyeta_tools.llm_serve import process

            return process(args, cfg)
        else:
            raise Exception(args.llm_command)
    else:
        raise Exception(args.command)


if __name__ == "__main__":
    sys.exit(main())
