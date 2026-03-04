# SPDX-License-Identifier: MPL-2.0
import base64
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image

from adhyeta_tools.config import Config

start_time = time.time()
completed_times = []
processing_times = []
total_images = 0
first_result_time = 0
output_dir = "/tmp"
last_eta = 0


@dataclass
class TaskResponse:
    image_name: str
    md_name: str
    md_path: Path
    processing_time: int
    total_time: int
    completed_at: int
    prompt_tokens: int
    output_tokens: int
    total_tokens: int
    finish_reason: str
    text: str


def elapsed_ts(start):
    return time.time() - start


def fmt_t(n):
    return f"{n:.1f}s"


def ocr_image(image_path: Path, cfg: Config) -> TaskResponse:
    with Image.open(image_path) as img:
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode()

    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                    {"type": "text", "text": cfg.prompt},
                ],
            }
        ]
    }

    resp_start = time.time()

    resp = requests.post(f"http://{cfg.llm_host}:{cfg.llm_port}/v1/chat/completions", json=payload).json()
    out_path = Path(output_dir) / f"{image_path.stem}.md"

    return TaskResponse(
        image_name=image_path.name,
        md_name=out_path.name,
        md_path=out_path,
        processing_time=elapsed_ts(resp_start),
        total_time=int(time.time() - start_time),
        completed_at=int(time.time()),
        text=resp["choices"][0]["message"]["content"],
        finish_reason=resp["choices"][0]["finish_reason"],
        prompt_tokens=resp["usage"].get("prompt_tokens", 0),
        output_tokens=resp["usage"].get("completion_tokens", 0),
        total_tokens=resp["usage"].get("total_tokens", 0),
    )


def run_job(images: list, parallel: int, cfg: Config):
    global first_result_time
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        # Submit all tasks and track by future
        future_to_image = {executor.submit(ocr_image, img, cfg): img for img in images}

        last_result_time = None

        # Process as they complete
        for i, future in enumerate(as_completed(future_to_image), 1):
            result = future.result()
            current_time = time.time()

            time_stats = ""
            if not first_result_time:
                first_result_time = current_time
                time_stats += f" ({fmt_t(first_result_time - start_time)})"
            else:
                assert last_result_time is not None
                time_since_last = current_time - last_result_time
                time_stats += f" ({fmt_t(time_since_last)})"

            last_result_time = current_time
            completed_times.append(current_time)
            processing_times.append(result.processing_time)

            # Show progress - using throughput-based ETA
            throughput = i / (current_time - start_time)  # jobs per second
            eta = (total_images - i) / throughput
            global last_eta
            eta = min(eta, last_eta if last_eta else eta)
            last_eta = eta

            log = f"{i}/{total_images} | ETA: {int(eta)}s | {result.image_name} -> {result.md_name} {time_stats}"

            # Check for truncation using finish_reason
            if result.finish_reason == "length":
                flag = "⚠️ "
                log += f" | TRUNCATION. Hit {result.total_tokens} token limit"
            elif result.finish_reason == "stop":
                flag = "✅ "
                result.md_path.parent.mkdir(exist_ok=True)
                result.md_path.write_text(result.text)
            else:
                flag = "⚠️ "
                log += f" | Unknown finish_reason: {result.finish_reason}"
            print(flag + log)


def print_final():
    # Calculate final statistics
    total_time = time.time() - start_time

    print("\n" + "=" * 50)
    print("FINAL STATISTICS")
    print("=" * 50)
    print(f"📊 Total images processed: {total_images}")
    print(f"⏱️ Time to first result: {fmt_t(first_result_time - start_time)}")
    print(f"📈 Average time per image: {fmt_t(total_time / total_images)}")
    print(f"📉 Average processing time (API call only): {fmt_t(sum(processing_times) / len(processing_times))}")
    print(f"⚡ Total wall clock time: {fmt_t(total_time)}")
    print(f"🚀 Effective throughput: {total_images / total_time:.2f} images/sec")

    # Calculate deltas between completions
    if len(completed_times) > 1:
        deltas = [completed_times[i] - completed_times[i - 1] for i in range(1, len(completed_times))]
        print(
            f"📊 Delta stats: min={fmt_t(min(deltas))}, max={fmt_t(max(deltas))}, avg={fmt_t(sum(deltas) / len(deltas))}"
        )


def process(args, cfg: Config):
    # Only process images without  corresponding .md files
    texts = [x.stem for x in list(Path(args.output_dir).glob("**/*")) if x.suffix in ".md".split(" ")]

    images = [
        x for x in list(Path(args.input_dir).glob("**/*")) if x.suffix in ".png .jpg".split(" ") and x.stem not in texts
    ]

    global total_images
    total_images = len(images)
    global output_dir
    output_dir = args.output_dir

    if not total_images:
        print(f"no images found in {args.input_dir}")
    else:
        cfg.prompt = args.prompt if args.prompt else cfg.prompt
        print(f"Processing {total_images} images with {args.parallel} concurrent workers")
        run_job(images, args.parallel, cfg)
        print_final()
    return 0
