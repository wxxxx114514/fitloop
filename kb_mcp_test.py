# -*- coding: utf-8 -*-
"""最小 MCP 连通性测试：起 server → initialize → call 一次 → 打印。"""
import asyncio, os, sys, time, json
sys.stdout.reconfigure(encoding="utf-8")

KB_PY = r"D:\project\fitloop-kb\.venv\Scripts\python.exe"
KB_DIR = r"D:\project\fitloop-kb"

async def main():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    t0 = time.time()
    params = StdioServerParameters(command=KB_PY, args=["-m", "kb.server"], cwd=KB_DIR,
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    print("启动 server...", flush=True)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as sess:
            print(f"管道已建立 {time.time()-t0:.1f}s", flush=True)
            await sess.initialize()
            print(f"initialize 完成 {time.time()-t0:.1f}s", flush=True)
            tools = await sess.list_tools()
            print("工具:", [t.name for t in tools.tools], flush=True)
            res = await sess.call_tool("search_guideline", {"query": "每天奶类摄入多少", "k": 5})
            print(f"调用完成 {time.time()-t0:.1f}s", flush=True)
            txt = res.content[0].text
            data = json.loads(txt)
            for x in data.get("results", []):
                print(f"  p{x['page']} {x['text'][:50]}", flush=True)

asyncio.run(main())