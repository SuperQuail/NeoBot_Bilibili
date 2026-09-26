# NeoBot_StreamingParser

NeoBot 的 B 站数据解析插件：把 [@ikenxuan/amagi](https://github.com/ikenxuan/amagi) 里以 TypeScript 实现的 B 站 Web 接口协议，用**尽可能纯 Python** 的方式重新实现。

> 当前状态：**空壳骨架（v0.1.0）**。插件可以被 NeoBot 直接识别、加载、启停，但还没有任何解析能力；协议实现见 [docs/roadmap.md](docs/roadmap.md)。

## 安装

插件目录就是本仓库根目录，把整个目录放进 NeoBot 的插件文件夹即可：

```text
<NeoBot>/app/data/plugins/streaming_parser/
```

NeoBot 启动时会扫描插件目录，发现含 `__init__.py` 且导出 `plugin = Plugin(...)` 的目录并加载
（第三方插件目录由 `[plugins].dir` 决定，默认 `./plugins`，相对数据目录解析）。
本仓库 `plugin.toml` 的 name / version 必须与 `Plugin("streaming_parser")` 一致，
`repo` 字段指向本站，面板用它做更新检查。

## 配置

配置项在 `plugin.toml` 的 `[config]` 中作为打包默认值，用户实际配置落在
`<NeoBot>/app/data/plugins_data/streaming_parser/config.toml`：

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `request_timeout` | float | 10.0 | 单次 HTTP 请求超时（秒） |
| `cookie` | str | 空 | B 站 Cookie 串，留空表示匿名请求 |
| `user_agent` | str | 空 | 自定义 UA，留空用内置默认值 |

## 目录结构

```text
.
├── plugin.toml          # NeoBot 插件清单（运行时元数据）
├── __init__.py          # 插件入口：导出 plugin = Plugin(...)
├── docs/
│   ├── roadmap.md       # 移植路线图（P0/P1/P2）与参考项目能力边界
│   └── frontend.md      # 前端预编译策略（部署侧不装 Node）
├── .github/workflows/   # 轻量 CI：校验清单与语法
├── research/            # 【不入库】技术验证与测试目录，见 .gitignore
├── frontend/            # 前端源码（未来，Vite），不入包
└── web/                 # 前端构建产物（未来），必须入库
```

## 开发约定

- **纯 Python 优先**：协议、解析、签名、数据模型全部用 Python 写；只有确实需要在浏览器里
  跑的东西才写前端，并且必须预编译。
- **部署侧零前端工具链**：最终用户不需要 Node/pnpm，构建产物 `web/` 随仓库分发，
  详见 [docs/frontend.md](docs/frontend.md)。
- **技术验证放在 `research/`**（已 gitignore）：协议原型、对照测试、抓包样本都放那里，
  结论成熟后再搬进正式代码。
- 参考项目 amagi 是本插件的协议来源，但它**没有实现直播弹幕长连接**，
  P2 的协议规格必须另行调研，不能以 amagi 为依据。

## 许可证

[MIT](LICENSE)
