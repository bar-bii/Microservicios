from __future__ import annotations

import argparse
from pathlib import Path

BOUNDARY = "----MicroserviciosVegetaBoundary"
PDF_NAMES = ("small.pdf", "medium.pdf", "large.pdf", "xlarge.pdf")


def multipart_body(filename: str, pdf_bytes: bytes) -> bytes:
    header = (
        f"--{BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/pdf\r\n"
        "\r\n"
    ).encode("ascii")
    footer = f"\r\n--{BOUNDARY}--\r\n".encode("ascii")
    return header + pdf_bytes + footer


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    pdf_dir = repo_root / "tests" / "stress" / "pdfs"
    payload_dir = repo_root / "tests" / "stress" / "vegeta" / "payloads"
    targets_path = repo_root / "tests" / "stress" / "vegeta" / "targets.txt"

    parser = argparse.ArgumentParser(description="Build multipart Vegeta targets.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080",
        help="Base URL used in the generated targets file.",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    missing = [name for name in PDF_NAMES if not (pdf_dir / name).is_file()]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(f"Faltan PDFs en {pdf_dir}: {names}. Ejecuta make stress-corpus.")

    payload_dir.mkdir(parents=True, exist_ok=True)

    target_blocks: list[str] = []
    for name in PDF_NAMES:
        pdf_bytes = (pdf_dir / name).read_bytes()
        body = multipart_body(name, pdf_bytes)
        payload_path = payload_dir / f"{name}.multipart"
        payload_path.write_bytes(body)

        relative_payload = payload_path.relative_to(repo_root).as_posix()
        target_blocks.append(
            "\n".join(
                [
                    f"POST {base_url}/extract",
                    f"Content-Type: multipart/form-data; boundary={BOUNDARY}",
                    f"@{relative_payload}",
                ]
            )
        )
        print(
            f"{name}: pdf={len(pdf_bytes)} bytes, "
            f"multipart={len(body)} bytes (+{len(body) - len(pdf_bytes)} overhead)"
        )

    targets_path.write_text("\n\n".join(target_blocks) + "\n", encoding="utf-8")
    print(f"targets: {targets_path.relative_to(repo_root)}")


if __name__ == "__main__":
    main()
