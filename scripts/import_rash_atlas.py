#!/usr/bin/env python3
"""Import the standalone rash atlas into the teaching workbench.

The source site keeps its clinical content in one HTML file. This script turns
that content into structured JSON and copies the web-sized teaching images so
the integrated app can search, filter, compare, and attribute every image.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from lxml import html


def class_xpath(name: str) -> str:
    return f'contains(concat(" ", normalize-space(@class), " "), " {name} ")'


def text(node) -> str:
    return " ".join(node.text_content().split()) if node is not None else ""


def parse_atlas(source_dir: Path) -> dict:
    document = html.fromstring((source_dir / "index.html").read_text(encoding="utf-8"))
    categories: list[dict] = []
    disease_total = 0
    image_total = 0

    for category_node in document.xpath(f'//section[{class_xpath("catsec")}]'):
        heading_nodes = category_node.xpath("./h2")
        full_title = text(heading_nodes[0]) if heading_nodes else "未分类"
        short_title = re.sub(r"^[一二三四五六七八九十]+、", "", full_title)
        diseases: list[dict] = []

        for disease_node in category_node.xpath(f'./section[{class_xpath("dis")}]'):
            heading_nodes = disease_node.xpath("./h3")
            heading = heading_nodes[0] if heading_nodes else None
            english_nodes = heading.xpath(f'.//span[{class_xpath("en")}]') if heading is not None else []
            name = (heading.text or "").strip() if heading is not None else "未命名病种"
            english = text(english_nodes[0]) if english_nodes else ""

            facts: dict[str, str] = {}
            for row in disease_node.xpath(f'./table[{class_xpath("facts")}]/tr'):
                header = row.xpath("./th")
                value = row.xpath("./td")
                if header and value:
                    facts[text(header[0])] = text(value[0])

            images: list[dict] = []
            for figure in disease_node.xpath(f'./div[{class_xpath("grid")}]/figure'):
                image_nodes = figure.xpath(".//img")
                if not image_nodes:
                    continue
                image_node = image_nodes[0]
                image_name = Path(image_node.get("src", "")).name
                source_image = source_dir / "images" / image_name
                if not source_image.exists():
                    raise FileNotFoundError(f"Missing atlas image: {source_image}")

                meta_nodes = figure.xpath(f'.//div[{class_xpath("meta")}]')
                meta = meta_nodes[0] if meta_nodes else None
                source_labels = meta.xpath("./b") if meta is not None else []
                license_nodes = meta.xpath(f'./span[{class_xpath("lic")}]') if meta is not None else []
                spans = meta.xpath("./span") if meta is not None else []
                caption_nodes = figure.xpath(f'.//p[{class_xpath("cap")}]')
                provider_nodes = figure.xpath(f'.//div[{class_xpath("src")}]')

                links = [
                    {"label": text(anchor), "url": anchor.get("href", "")}
                    for anchor in figure.xpath(".//a[@href]")
                ]
                image = {
                    "file": image_name,
                    "alt": image_node.get("alt", f"{name}皮疹"),
                    "width": int(image_node.get("width", "0") or 0),
                    "height": int(image_node.get("height", "0") or 0),
                    "source_label": text(source_labels[0]) if source_labels else "来源见清单",
                    "license": text(license_nodes[0]) if license_nodes else "来源见清单",
                    "dimensions": text(spans[-1]) if spans else "",
                    "caption": text(caption_nodes[0]) if caption_nodes else "",
                    "provider": text(provider_nodes[0]) if provider_nodes else "",
                    "links": links,
                    "textbook": "bookcard" in (figure.get("class") or "").split(),
                }
                images.append(image)

            diseases.append(
                {
                    "id": disease_node.get("id", re.sub(r"\W+", "-", english.lower()).strip("-")),
                    "name": name,
                    "english": english,
                    "facts": facts,
                    "images": images,
                    "image_count": len(images),
                    "search_text": " ".join([name, english, *facts.values()]),
                }
            )
            disease_total += 1
            image_total += len(images)

        categories.append(
            {
                "id": category_node.get("id", f"category-{len(categories) + 1}"),
                "title": short_title,
                "full_title": full_title,
                "diseases": diseases,
                "disease_count": len(diseases),
                "image_count": sum(item["image_count"] for item in diseases),
            }
        )

    return {
        "title": "临床常见皮疹图谱",
        "version": "2026-08-25",
        "summary": {
            "category_count": len(categories),
            "disease_count": disease_total,
            "image_count": image_total,
        },
        "notice": "图谱用于医学教学与鉴别思路训练，不能替代面诊、病理或实验室诊断。教材图片版权归出版社与原作者，仅供教学参考。",
        "provenance": [
            "教材：《皮肤性病学》第10版（人民卫生出版社，2024），版权归出版社与原作者。",
            "CDC PHIL：仅收录经原站核对为公有领域的图像。",
            "PubMed Central：仅收录 CC BY / CC0 开放许可文献配图。",
        ],
        "categories": categories,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Path to the standalone rash-atlas directory")
    parser.add_argument("target", type=Path, help="Target assets/rash-atlas directory")
    args = parser.parse_args()

    source = args.source.resolve()
    target = args.target.resolve()
    target.mkdir(parents=True, exist_ok=True)

    atlas = parse_atlas(source)
    (target / "atlas.json").write_text(
        json.dumps(atlas, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copytree(source / "images", target / "images", dirs_exist_ok=True)
    source_ledger = (source / "来源清单.csv").read_text(encoding="utf-8-sig")
    (target / "sources.csv").write_text(source_ledger, encoding="utf-8", newline="\n")

    summary = atlas["summary"]
    print(
        f"Imported {summary['category_count']} categories, "
        f"{summary['disease_count']} diseases, {summary['image_count']} images"
    )


if __name__ == "__main__":
    main()
