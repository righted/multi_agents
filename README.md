# 婚礼多智能体

一个网页版的婚礼策划助手。用户说清楚城市、目的地、人数、风格和婚期，它会分头查航班、找场地、挑歌单，最后拼成一套完整方案。

在线演示：https://agent.langxo.com
(test/test)

## 四个 agent 分工

协调员是主 agent，负责和用户聊，把出发地、目的地、人数、风格、婚期五个信息凑齐，写进会话状态，然后决定什么时候往下派活。

航班专家拿到出发地和目的地，调远程 MCP 查航班，返回班次、时长和参考价。查过的结果会缓存十二小时，同样的航线和日期不会重复打接口。

场地专家用 Tavily 搜香格里拉一带适合办婚礼的酒店、草坪和庄园，把候选场地、容量、报价整理成一段话。

音乐专家在 SQLite 的 Chinook 示例库里查曲目，按风格凑一份能排下来的歌单。

## 页面上能看到什么

打开先登录，账号由服务端预置，不开放注册。登录后左边是历史会话列表，可以切换，也可以新建；每条会话的记忆都存在 SQLite 里，关掉网页再来还能接上。

回复过程中会实时显示三段信息：模型的思考过程（折叠，点开看原文）、每次工具调用的名称和耗时、以及调用返回的摘要。正文按 Markdown 渲染，标题、表格、代码块都能正常显示。

## 目录

```
app/
  main.py              FastAPI 入口，启动时建 agent 和数据库
  api/v1/chat.py       对话、历史、会话列表三个接口
  api/v1/auth.py       登录、当前用户
  agents/wedding.py    四个 agent 的组装和流式输出
  agents/llm.py        让思考过程能从流里透出来
  core/auth.py         密码哈希和 JWT
  db/                  用户、会话索引、缓存三张表
  static/index.html    单页界面
mcp/math_server.py     自定义的加减法 MCP
data/Chinook.db        音乐示例库
```

## 本地运行

装依赖：`pip install -r requirements.txt`，或者用 uv。

在项目根目录建 `.env`，填下面这些，然后 `py -m uvicorn app.main:app --port 8001`，浏览器打开 http://127.0.0.1:8001。

## 环境变量

| 变量 | 用途 |
| --- | --- |
| LLM_MODEL_ID / LLM_API_KEY / LLM_BASE_URL | 对话模型，走 OpenAI 兼容接口 |
| Tavily_API_KEY | 场地搜索的备用通道 |
| Tavily_Hikari_Token | 搜索 MCP 中转站的令牌 |
| JWT_SECRET_KEY | 登录令牌签名用，部署前换成随机串 |
| ADMIN_PASSWORD / TEST_PASSWORD | 两个预置账号的密码 |
| CACHE_TTL | 航班缓存秒数，默认 43200 |


## 用 Docker 部署

```
docker compose up -d --build
```
