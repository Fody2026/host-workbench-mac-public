#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包前 API Key / 凭据扫描。

任何版本、任何电脑打包前都必须通过：
    python tools/secret_scan.py --root .
发现疑似 Key 时退出码为 1，打包脚本应终止。
"""
import argparse
import os
import re
import sys

SKIP_DIRS = {".git", "__pycache__", "build", "dist", "data", "logs", "backups",
             "node_modules", ".venv", "venv", "env", "cache", "tmp"}
TEXT_EXTS = {".py", ".js", ".json", ".yaml", ".yml", ".txt", ".ini", ".cfg",
             ".env", ".md", ".html", ".htm", ".xml", ".toml"}
PATTERNS = [
    ("OpenAI/DeepSeek key", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("Anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("Google key", re.compile(r"AIza[0-9A-Za-z_\-]{20,}")),
    ("GitHub token", re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("AWS key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Bearer token", re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}")),
    ("quoted api_key", re.compile(r"api[_-]?key\s*[:=]\s*['\"][^'\"]{12,}")),
    ("env api key", re.compile(r"(DEEPSEEK|OPENAI|ANTHROPIC|VOLC|QWEN|DASHSCOPE)_API_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}")),
]
FORBIDDEN_NAMES = {"ci_tokens.json", "github_token.txt", "gh_token.txt",
                   ".env", "settings.json", "credentials.json"}


def mask(s: str) -> str:
    return re.sub(r"(sk-|ghp_|github_pat_|AIza|AKIA|xox[baprs]-)[A-Za-z0-9_\-]+",
                  r"\1***", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--warn-only", action="store_true")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    hits = []
    warnings = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".git")]
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root)
            if fn in FORBIDDEN_NAMES:
                warnings.append((rel, 0, "禁止打包的凭据/设置文件"))
            if os.path.splitext(fn)[1].lower() not in TEXT_EXTS:
                continue
            try:
                text = open(p, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                for label, pat in PATTERNS:
                    if pat.search(line):
                        hits.append((rel, i, label, mask(line.strip())[:180]))
    for w in warnings:
        print("WARN", *w)
    for h in hits:
        print("FOUND", *h)
    print(f"scanned root={root} findings={len(hits)} warnings={len(warnings)}")
    if hits and not args.warn_only:
        print("打包已终止：请删除/改为运行时输入后再打包。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
