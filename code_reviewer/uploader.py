"""上传模块：将评审报告（Markdown）上传到 i 讯飞云文档。

支持两种模式（config/upload.json 配置）：
1. "webhook": 调用团队提供的内容 API（POST JSON，携带 api_token）。
2. "lark_cli": 若本机安装了 Lark Cli（i讯飞版），自动调用其命令新建文档并写入内容。
   常见命令形如 `lark-cli doc create --title X --content-file report.md`，
   可通过 upload.json 的 cli_command 定制。

注意：因云文档权限/认证属于团队内网配置，实际填好 config/upload.json 后即可直接使用；
未配置时工具仅提示，不影响本地评审链路。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.request
from typing import Any, Dict, Optional

from .config import REPO_ROOT, _load_json
from .logger import get_logger

log = get_logger()
DEFAULT_UPLOAD_CONFIG = REPO_ROOT + "/config/upload.json"


class UploadError(Exception):
    pass


def load_upload_config(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    p = path or DEFAULT_UPLOAD_CONFIG
    try:
        cfg = _load_json(p)
    except Exception as e:
        log.warning("上传配置不可用（%s），跳过上传: %s", p, e)
        return None
    return cfg


def upload_markdown(markdown_text: str, title: str, config_path: Optional[str] = None) -> str:
    """上传 Markdown 报告，返回文档链接或说明字符串。"""
    cfg = load_upload_config(config_path)
    if not cfg:
        raise UploadError("未配置 config/upload.json，无法上传云文档（可在配置后重试）")
    mode = cfg.get("mode", "webhook")

    if mode == "webhook":
        endpoint = cfg.get("endpoint")
        token = cfg.get("api_token", "")
        if not endpoint:
            raise UploadError("upload.json 中缺少 endpoint")
        payload = {
            "title": title,
            "content": markdown_text,
            "content_type": "markdown",
            "api_token": token,
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        log.info("上传成功: %s", body[:200])
        return body

    if mode == "lark_cli":
        cmd_tpl = cfg.get("cli_command") or "lark-cli doc create --title {title} --content-stdin"
        cli = cmd_tpl.split()[0]
        if not shutil.which(cli):
            raise UploadError(
                f"未找到命令 `{cli}`。请安装 Lark Cli（i讯飞版）并完成统一认证，"
                "或在 config/upload.json 中改用 webhook 模式"
            )
        cmd = cmd_tpl.format(title=title).split()
        proc = subprocess.run(
            cmd, input=markdown_text.encode("utf-8"), capture_output=True, timeout=120
        )
        if proc.returncode != 0:
            raise UploadError(f"云文档命令执行失败: {proc.stderr.decode('utf-8', errors='replace')[:300]}")
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        log.info("上传成功: %s", out[:200])
        return out

    raise UploadError(f"未知上传模式: {mode}")
