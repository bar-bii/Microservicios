from __future__ import annotations

import argparse
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from reportlab.pdfgen import canvas

PAGE_SIZE = (595, 842)
MARGIN = 40
TEXT = (
    "Synthetic deterministic content for reproducible PDF extraction benchmarks. "
    "The same bytes are generated on every run so throughput and latency results "
    "can be compared across deployments."
)


@dataclass(frozen=True)
class Profile:
    filename: str
    target_bytes: int
    font_size: int
    leading: int
    lines_per_page: int


PROFILES = (
    Profile("small.pdf", 50 * 1024, 12, 18, 22),
    Profile("medium.pdf", 1 * 1024**2, 10, 14, 45),
    Profile("large.pdf", 4 * 1024**2, 9, 12, 60),
    Profile("xlarge.pdf", 9 * 1024**2, 8, 10, 76),
)


def render(profile: Profile, pages: int) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(
        buffer,
        pagesize=PAGE_SIZE,
        pageCompression=0,
        invariant=1,
    )
    pdf.setTitle(f"Stress corpus: {profile.filename}")
    pdf.setAuthor("Microservicios")
    pdf.setSubject("Synthetic PDF corpus for load and stress testing")
    pdf.setCreator("tests/stress/generate_corpus.py")
    pdf.setKeywords(["synthetic", "stress", "pdf"])

    top = PAGE_SIZE[1] - MARGIN
    for page in range(pages):
        pdf.setFont("Helvetica", profile.font_size)
        y = top
        for line in range(profile.lines_per_page):
            pdf.drawString(
                MARGIN,
                y,
                f"p{page + 1:05d} l{line + 1:03d} {TEXT}",
            )
            y -= profile.leading
        pdf.showPage()

    pdf.save()
    return buffer.getvalue()


def build(profile: Profile) -> tuple[bytes, int]:
    sample_pages = 4
    sample = render(profile, sample_pages)
    bytes_per_page = max(len(sample) // sample_pages, 1)
    pages = max(1, round(profile.target_bytes / bytes_per_page))

    data = sample
    for _ in range(4):
        data = render(profile, pages)
        if 0.95 <= len(data) / profile.target_bytes <= 1.05:
            break
        pages = max(1, round(pages * profile.target_bytes / len(data)))

    return data, pages


def write_readme(output_dir: Path, rows: list[tuple[Profile, int, bytes]]) -> None:
    lines = [
        "# Corpus sintético",
        "",
        "Generado por `make stress-corpus`. No editar a mano: los PDFs son",
        "deterministas y se regeneran con el mismo contenido y hashes.",
        "",
        "| Archivo | Objetivo | Páginas | Bytes | SHA-256 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for profile, pages, data in rows:
        lines.append(
            f"| `{profile.filename}` | ~{profile.target_bytes} | {pages} | "
            f"{len(data)} | `{hashlib.sha256(data).hexdigest()}` |"
        )
    lines.extend(
        [
            "",
            "Los binarios están ignorados por Git. Regenerar con:",
            "",
            "```bash",
            "make stress-corpus",
            "```",
            "",
        ]
    )
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Generate the deterministic stress corpus.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "tests" / "stress" / "pdfs",
        help="Directory where the PDFs and README.md are written.",
    )
    args = parser.parse_args()

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[Profile, int, bytes]] = []
    for profile in PROFILES:
        data, pages = build(profile)
        (output_dir / profile.filename).write_bytes(data)
        rows.append((profile, pages, data))
        digest = hashlib.sha256(data).hexdigest()
        print(f"{profile.filename}: {len(data)} bytes, {pages} pages, sha256={digest}")

    write_readme(output_dir, rows)


if __name__ == "__main__":
    main()
