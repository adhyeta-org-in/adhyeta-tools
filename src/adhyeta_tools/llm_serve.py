# SPDX-License-Identifier: MPL-2.0
import subprocess

from adhyeta_tools.config import Config


def process(args, cfg: Config):
    # Calculate total context
    ctx_size = args.parallel * args.ctx_size_per

    # Build command
    cmd = [
        "llama-server",
        "--model",
        cfg.model_path,
        "--mmproj",
        cfg.mmproj_path,
        "--batch-size",
        str(args.batch_size),
        "--ctx-size",
        str(ctx_size),
        "--parallel",
        str(args.parallel),
        "--gpu-layers",
        "99",
        "--device",
        cfg.device,
        "--image-min-tokens",
        "1024",
        "--host",
        cfg.llm_host,
        "--port",
        str(cfg.llm_port),
    ]

    # Show configuration
    print("\n🚀 Launching llama-server with:")
    print(f"   Model: {cfg.model_path}")
    print(f"   Parallel slots: {args.parallel}")
    print(f"   Batch size: {args.batch_size}")
    print(f"   Context per slot: {args.ctx_size_per}")
    print(f"   Total context: {ctx_size}")
    print(f"   Device: {cfg.device}")
    print(f"   Port: {cfg.llm_port}")

    print("\n🔄 Starting server... (Ctrl+C to stop)\n")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")
    except FileNotFoundError:
        print("\n❌ Error: 'llama-server' not found in PATH")
        print("   Make sure llama.cpp is installed and in your PATH")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1

    return 0
