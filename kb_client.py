# -*- coding: utf-8 -*-
"""fitloop 侧的 kb 客户端：MCP over stdio，带超时与降级。

降级约定（和 kb 的边界一致）：
- kb 正常     → 返回带 source/page 的片段
- 超时/挂掉   → degraded=True，调用方退回纯计算，不解释原因
- 检索为空    → results=[]，调用方应明确说「我这儿没有依据」
"""
import asyncio, os, sys, json

KB_PY = r"D:\project\fitloop-kb\.venv\Scripts\python.exe"
KB_DIR = r"D:\project\fitloop-kb"
DEFAULT_TIMEOUT = 3.0


class KBClient:
    def __init__(self, python=KB_PY, cwd=KB_DIR, timeout=DEFAULT_TIMEOUT):
        self.python, self.cwd, self.timeout = python, cwd, timeout

    def _available(self):
        return os.path.exists(self.python) and os.path.isdir(self.cwd)

    async def _call(self, tool, args):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=self.python, args=["-m", "kb.server"], cwd=self.cwd,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as sess:
                await sess.initialize()
                res = await sess.call_tool(tool, args)
                return res

    def search(self, query, k=5):
        """同步入口：给 Agent 用。任何异常都降级，不抛。"""
        if not self._available():
            return {"degraded": True, "why": "kb 不可用", "results": []}
        try:
            res = asyncio.run(asyncio.wait_for(self._call("search_guideline", {"query": query, "k": k}),
                                               timeout=self.timeout))
        except asyncio.TimeoutError:
            return {"degraded": True, "why": f"超时 {self.timeout}s", "results": []}
        except Exception as e:
            return {"degraded": True, "why": f"{type(e).__name__}: {str(e)[:60]}", "results": []}

        # MCP 结果在 res.content[0].text（JSON 串）
        try:
            data = json.loads(res.content[0].text)
        except Exception:
            return {"degraded": True, "why": "返回格式解析失败", "results": []}
        return {"degraded": False, "results": data.get("results", [])}


if __name__ == "__main__":
    c = KBClient()
    for q in ["每天奶类摄入多少", "维生素D补多少"]:
        r = c.search(q)
        print(f"\n问：{q}")
        if r["degraded"]:
            print("  降级:", r["why"])
        elif not r["results"]:
            print("  无结果（应拒答）")
        else:
            for x in r["results"][:2]:
                print(f"  p{x['page']} ({x['source']}) {x['text'][:60]}")
