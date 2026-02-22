#!/usr/bin/env python3
"""
rewrite-github-urls.py — GitHub Pages 部署前处理脚本

将 _site/ 中 .pw.toml 的 github.com 下载链接改写为反代链接，
并重新计算 index.toml 和 pack.toml 中的 SHA256 哈希。

仅用于 GitHub Actions CI 部署流程，不修改源码仓库中的文件。

用法:
    python3 scripts/rewrite-github-urls.py [--site-dir _site] [--proxy-prefix URL]
"""

import argparse
import hashlib
import pathlib
import re
import sys


# ── 默认配置 ──
DEFAULT_SITE_DIR = "_site"
DEFAULT_PROXY_PREFIX = "https://ghfast.top/github.com"
GITHUB_URL_PATTERN = r'(url\s*=\s*")https://github\.com/'


def rewrite_download_urls(mods_dir: pathlib.Path, proxy_prefix: str) -> int:
    """将 mods/*.pw.toml 中 github.com 下载链接改写为反代链接。

    返回被改写的文件数量。
    """
    count = 0
    pattern = re.compile(GITHUB_URL_PATTERN)
    replacement = rf"\g<1>{proxy_prefix}/"

    for f in sorted(mods_dir.glob("*.pw.toml")):
        text = f.read_text(encoding="utf-8")
        if pattern.search(text):
            new_text = pattern.sub(replacement, text)
            f.write_text(new_text, encoding="utf-8")
            print(f"  [改写] {f.name}")
            count += 1

    return count


def rehash_index(site_dir: pathlib.Path) -> bool:
    """重新计算 index.toml 中每个文件条目的 SHA256 哈希。

    返回是否有哈希发生变更。
    """
    index_path = site_dir / "index.toml"
    if not index_path.exists():
        print("  [跳过] index.toml 不存在")
        return False

    index_text = index_path.read_text(encoding="utf-8")

    # 按 [[files]] 块拆分
    blocks = re.split(r"(?=^\[\[files\]\])", index_text, flags=re.MULTILINE)
    new_blocks = []
    changed = False

    for block in blocks:
        m_file = re.search(r'file\s*=\s*"([^"]+)"', block)
        m_hash = re.search(r'hash\s*=\s*"([a-f0-9]+)"', block)
        if m_file and m_hash:
            fpath = site_dir / m_file.group(1)
            if fpath.exists():
                new_hash = hashlib.sha256(fpath.read_bytes()).hexdigest()
                if new_hash != m_hash.group(1):
                    block = block.replace(
                        m_hash.group(0), f'hash = "{new_hash}"'
                    )
                    print(
                        f"  [哈希更新] {fpath.name}: "
                        f"{m_hash.group(1)[:12]}... -> {new_hash[:12]}..."
                    )
                    changed = True
        new_blocks.append(block)

    if changed:
        index_path.write_text("".join(new_blocks), encoding="utf-8")
    return changed


def rehash_pack(site_dir: pathlib.Path) -> None:
    """更新 pack.toml 中 index.toml 的 SHA256 哈希。"""
    pack_path = site_dir / "pack.toml"
    index_path = site_dir / "index.toml"

    if not pack_path.exists() or not index_path.exists():
        return

    new_index_hash = hashlib.sha256(index_path.read_bytes()).hexdigest()
    pack_text = pack_path.read_text(encoding="utf-8")

    # 精确定位 [index] 区块内的 hash 字段，避免误改其他区块
    m = re.search(
        r'(\[index\].*?hash\s*=\s*")[a-f0-9]+(")',
        pack_text,
        re.DOTALL,
    )
    if m:
        new_pack_text = (
            pack_text[: m.start()]
            + m.group(1)
            + new_index_hash
            + m.group(2)
            + pack_text[m.end() :]
        )
    else:
        print("  [警告] 未在 pack.toml 中找到 [index] hash 字段")
        return

    if new_pack_text != pack_text:
        pack_path.write_text(new_pack_text, encoding="utf-8")
        print(f"  [哈希更新] pack.toml -> index.toml: {new_index_hash[:12]}...")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="改写 packwiz 部署产物中的 GitHub 下载链接并重算哈希"
    )
    parser.add_argument(
        "--site-dir",
        default=DEFAULT_SITE_DIR,
        help=f"部署产物目录 (默认: {DEFAULT_SITE_DIR})",
    )
    parser.add_argument(
        "--proxy-prefix",
        default=DEFAULT_PROXY_PREFIX,
        help=f"反代 URL 前缀 (默认: {DEFAULT_PROXY_PREFIX})",
    )
    args = parser.parse_args()

    site_dir = pathlib.Path(args.site_dir)
    mods_dir = site_dir / "mods"

    if not site_dir.exists():
        print(f"[错误] 部署目录不存在: {site_dir}", file=sys.stderr)
        return 1

    # ── 步骤 1: 改写下载链接 ──
    print("=== 步骤 1: 改写 GitHub 下载链接 ===")
    if mods_dir.exists():
        count = rewrite_download_urls(mods_dir, args.proxy_prefix)
        print(f"共改写 {count} 个文件")
    else:
        count = 0
        print("  mods/ 目录不存在，跳过")

    # ── 步骤 2: 重算哈希（仅在有改写时） ──
    if count > 0:
        print("\n=== 步骤 2: 重新计算索引哈希 ===")
        changed = rehash_index(site_dir)
        if changed:
            rehash_pack(site_dir)
        print("哈希校验完成")
    else:
        print("\n无需重算哈希")

    return 0


if __name__ == "__main__":
    sys.exit(main())
